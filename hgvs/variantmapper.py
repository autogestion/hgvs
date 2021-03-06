# -*- coding: utf-8 -*-
"""Provides VariantMapper and EasyVariantMapper to project variants
between sequences using TranscriptMapper.

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import logging

from Bio.Seq import Seq
from bioutils.sequences import reverse_complement
import recordtype

import hgvs
import hgvs.location
import hgvs.normalizer
import hgvs.posedit
import hgvs.transcriptmapper
import hgvs.utils.altseq_to_hgvsp as altseq_to_hgvsp
import hgvs.utils.altseqbuilder as altseqbuilder
import hgvs.variant
import hgvs.validator

from hgvs.exceptions import HGVSError, HGVSDataNotAvailableError, HGVSUnsupportedOperationError, HGVSInvalidVariantError
from hgvs.decorators.lru_cache import lru_cache

_logger = logging.getLogger(__name__)


class VariantMapper(object):
    """Maps SequenceVariant objects between g., n., r., c., and p. representations.

    g⟷{c,n,r} projections are similar in that c, n, and r variants
    may use intronic coordinates. There are two essential differences
    that distinguish the three types:

    * Sequence start: In n and r variants, position 1 is the sequence
      start; in c variants, 1 is the transcription start site.
    * Alphabet: In n and c variants, sequences are DNA; in
      r. variants, sequences are RNA.

    This differences are summarized in this diagram::

      g ----acgtatgcac--gtctagacgt----      ----acgtatgcac--gtctagacgt----      ----acgtatgcac--gtctagacgt----
            \         \/         /              \         \/         /              \         \/         /
      c      acgtATGCACGTCTAGacgt         n      acgtatgcacgtctagacgt         r      acguaugcacgucuagacgu   
                 1                               1                                   1
      p          MetHisValTer

    The g excerpt and exon structures are identical. The g⟷n
    transformation, which is the most basic, accounts for the offset
    of the aligned sequences (shown with "1") and the exon structure.
    The g⟷c transformation is akin to g⟷n transformation, but
    requires an addition offset to account for the translation start
    site (c.1).  The CDS in uppercase. The g⟷c transformation is
    akin to g⟷n transformation with a change of alphabet.

    Therefore, this this code uses g⟷n as the core transformation
    between genomic and c, n, and r variants: All c⟷g and r⟷g
    transformations use n⟷g after accounting for the above
    differences. For example, c_to_g accounts for the transcription
    start site offset, then calls n_to_g.

    All methods require and return objects of type
    :class:`hgvs.variant.SequenceVariant`.

    """

    def __init__(self,
                 hdp,
                 replace_reference=False):
        """
        :param bool replace_reference: replace reference (entails additional network access)

        """

        self.hdp = hdp
        self.replace_reference = replace_reference


    # ############################################################################
    # g⟷t
    def g_to_t(self, var_g, tx_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        if not (var_g.type == "g"):
            raise HGVSInvalidVariantError("Expected a g. variant; got " + str(var_g))
        tm = self._fetch_TranscriptMapper(tx_ac=tx_ac, alt_ac=var_g.ac, alt_aln_method=alt_aln_method)
        if tm.is_coding_transcript:
            var_out = VariantMapper.g_to_c(self, var_g=var_g, tx_ac=tx_ac, alt_aln_method=alt_aln_method)
        else:
            var_out = VariantMapper.g_to_n(self, var_g=var_g, tx_ac=tx_ac, alt_aln_method=alt_aln_method)
        return var_out

    def t_to_g(self, var_t, alt_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        if var_t.type not in "cn":
            raise HGVSInvalidVariantError("Expected a c. or n. variant; got " + str(var_t))
        tm = self._fetch_TranscriptMapper(tx_ac=var_t.ac, alt_ac=alt_ac, alt_aln_method=alt_aln_method)
        if tm.is_coding_transcript:
            var_out = VariantMapper.c_to_g(self, var_c=var_t, alt_ac=alt_ac, alt_aln_method=alt_aln_method)
        else:
            var_out = VariantMapper.n_to_g(self, var_n=var_t, alt_ac=alt_ac, alt_aln_method=alt_aln_method)
        return var_out


    # ############################################################################
    # g⟷n
    def g_to_n(self, var_g, tx_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        """Given a parsed g. variant, return a n. variant on the specified
        transcript using the specified alignment method (default is
        "splign" from NCBI).

        :param hgvs.variant.SequenceVariant var_g: a variant object
        :param str tx_ac: a transcript accession (e.g., NM_012345.6 or ENST012345678)
        :param str alt_aln_method: the alignment method; valid values depend on data source
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`) using transcript (n.) coordinates
        :raises HGVSInvalidVariantError: if var_g is not of type "g"

        """

        if not (var_g.type == "g"):
            raise HGVSInvalidVariantError("Expected a g. variant; got " + str(var_g))
        tm = self._fetch_TranscriptMapper(tx_ac=tx_ac, alt_ac=var_g.ac, alt_aln_method=alt_aln_method)
        pos_n = tm.g_to_n(var_g.posedit.pos)
        edit_n = self._convert_edit_check_strand(tm.strand, var_g.posedit.edit)
        var_n = hgvs.variant.SequenceVariant(ac=tx_ac, type="n", posedit=hgvs.posedit.PosEdit(pos_n, edit_n))
        if self.replace_reference:
            self._replace_reference(var_n)
        return var_n

    def n_to_g(self, var_n, alt_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        """Given a parsed n. variant, return a g. variant on the specified
        transcript using the specified alignment method (default is
        "splign" from NCBI).

        :param hgvs.variant.SequenceVariant var_n: a variant object
        :param str alt_ac: a reference sequence accession (e.g., NC_000001.11)
        :param str alt_aln_method: the alignment method; valid values depend on data source
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`)
        :raises HGVSInvalidVariantError: if var_n is not of type "n"

        """

        if not (var_n.type == "n"):
            raise HGVSInvalidVariantError("Expected a n. variant; got " + str(var_n))
        tm = self._fetch_TranscriptMapper(tx_ac=var_n.ac, alt_ac=alt_ac, alt_aln_method=alt_aln_method)
        pos_g = tm.n_to_g(var_n.posedit.pos)
        edit_g = self._convert_edit_check_strand(tm.strand, var_n.posedit.edit)
        var_g = hgvs.variant.SequenceVariant(ac=alt_ac, type="g", posedit=hgvs.posedit.PosEdit(pos_g, edit_g))
        if self.replace_reference:
            self._replace_reference(var_g)
        return var_g

    # ############################################################################
    # g⟷c
    def g_to_c(self, var_g, tx_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        """Given a parsed g. variant, return a c. variant on the specified
        transcript using the specified alignment method (default is
        "splign" from NCBI).

        :param hgvs.variant.SequenceVariant var_g: a variant object
        :param str tx_ac: a transcript accession (e.g., NM_012345.6 or ENST012345678)
        :param str alt_aln_method: the alignment method; valid values depend on data source
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`) using CDS coordinates
        :raises HGVSInvalidVariantError: if var_g is not of type "g"

        """

        if not (var_g.type == "g"):
            raise HGVSInvalidVariantError("Expected a g. variant; got " + str(var_g))

        tm = self._fetch_TranscriptMapper(tx_ac=tx_ac, alt_ac=var_g.ac, alt_aln_method=alt_aln_method)
        pos_c = tm.g_to_c(var_g.posedit.pos)
        edit_c = self._convert_edit_check_strand(tm.strand, var_g.posedit.edit)
        var_c = hgvs.variant.SequenceVariant(ac=tx_ac, type="c", posedit=hgvs.posedit.PosEdit(pos_c, edit_c))
        if self.replace_reference:
            self._replace_reference(var_c)
        return var_c

    def c_to_g(self, var_c, alt_ac, alt_aln_method=hgvs.global_config.mapping.alt_aln_method):
        """Given a parsed c. variant, return a g. variant on the specified
        transcript using the specified alignment method (default is
        "splign" from NCBI).

        :param hgvs.variant.SequenceVariant var_c: a variant object
        :param str alt_ac: a reference sequence accession (e.g., NC_000001.11)
        :param str alt_aln_method: the alignment method; valid values depend on data source
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`)
        :raises HGVSInvalidVariantError: if var_c is not of type "c"

        """

        if not (var_c.type == "c"):
            raise HGVSInvalidVariantError("Expected a cDNA (c.); got " + str(var_c))

        tm = self._fetch_TranscriptMapper(tx_ac=var_c.ac, alt_ac=alt_ac, alt_aln_method=alt_aln_method)

        pos_g = tm.c_to_g(var_c.posedit.pos)
        edit_g = self._convert_edit_check_strand(tm.strand, var_c.posedit.edit)

        var_g = hgvs.variant.SequenceVariant(ac=alt_ac, type="g", posedit=hgvs.posedit.PosEdit(pos_g, edit_g))
        if self.replace_reference:
            self._replace_reference(var_g)
        return var_g

    # ############################################################################
    # c⟷n
    def c_to_n(self, var_c):
        """Given a parsed c. variant, return a n. variant on the specified
        transcript using the specified alignment method (default is
        "transcript" indicating a self alignment).

        :param hgvs.variant.SequenceVariant var_c: a variant object
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`)
        :raises HGVSInvalidVariantError: if var_c is not of type "c"

        """

        if not (var_c.type == "c"):
            raise HGVSInvalidVariantError("Expected a cDNA (c.); got " + str(var_c))
        tm = self._fetch_TranscriptMapper(tx_ac=var_c.ac, alt_ac=var_c.ac, alt_aln_method="transcript")
        pos_n = tm.c_to_n(var_c.posedit.pos)
        if (isinstance(var_c.posedit.edit, hgvs.edit.NARefAlt) or isinstance(var_c.posedit.edit, hgvs.edit.Dup) or
                isinstance(var_c.posedit.edit, hgvs.edit.Inv)):
            edit_n = copy.deepcopy(var_c.posedit.edit)
        else:
            raise HGVSUnsupportedOperationError("Only NARefAlt/Dup/Inv types are currently implemented")
        var_n = hgvs.variant.SequenceVariant(ac=var_c.ac, type="n", posedit=hgvs.posedit.PosEdit(pos_n, edit_n))
        if self.replace_reference:
            self._replace_reference(var_n)
        return var_n

    def n_to_c(self, var_n):
        """Given a parsed n. variant, return a c. variant on the specified
        transcript using the specified alignment method (default is
        "transcript" indicating a self alignment).

        :param hgvs.variant.SequenceVariant var_n: a variant object
        :returns: variant object (:class:`hgvs.variant.SequenceVariant`)
        :raises HGVSInvalidVariantError: if var_n is not of type "n"

        """

        if not (var_n.type == "n"):
            raise HGVSInvalidVariantError("Expected n. variant; got " + str(var_n))
        tm = self._fetch_TranscriptMapper(tx_ac=var_n.ac, alt_ac=var_n.ac, alt_aln_method="transcript")
        pos_c = tm.n_to_c(var_n.posedit.pos)
        if (isinstance(var_n.posedit.edit, hgvs.edit.NARefAlt) or isinstance(var_n.posedit.edit, hgvs.edit.Dup) or
                isinstance(var_n.posedit.edit, hgvs.edit.Inv)):
            edit_c = copy.deepcopy(var_n.posedit.edit)
        else:
            raise HGVSUnsupportedOperationError("Only NARefAlt/Dup/Inv types are currently implemented")
        var_c = hgvs.variant.SequenceVariant(ac=var_n.ac, type="c", posedit=hgvs.posedit.PosEdit(pos_c, edit_c))
        if self.replace_reference:
            self._replace_reference(var_c)
        return var_c

    # ############################################################################
    # c ⟶ p
    def c_to_p(self, var_c, pro_ac=None):
        """
        Converts a c. SequenceVariant to a p. SequenceVariant on the specified protein accession
        Author: Rudy Rico

        :param SequenceVariant var_c: hgvsc tag
        :param str pro_ac: protein accession
        :rtype: hgvs.variant.SequenceVariant

        """

        class RefTranscriptData(recordtype.recordtype("RefTranscriptData",
                                                      ["transcript_sequence", "aa_sequence", "cds_start", "cds_stop",
                                                       "protein_accession"])):
            @classmethod
            def setup_transcript_data(cls, hdp, tx_ac, pro_ac):
                """helper for generating RefTranscriptData from for c_to_p"""
                tx_info = hdp.get_tx_identity_info(var_c.ac)
                tx_seq = hdp.get_seq(tx_ac)

                if tx_info is None or tx_seq is None:
                    raise HGVSDataNotAvailableError("Missing transcript data for accession: {}".format(tx_ac))

                # use 1-based hgvs coords
                cds_start = tx_info["cds_start_i"] + 1
                cds_stop = tx_info["cds_end_i"]

                # padding list so biopython won't complain during the conversion
                tx_seq_to_translate = tx_seq[cds_start - 1:cds_stop]
                if len(tx_seq_to_translate) % 3 != 0:
                    "".join(list(tx_seq_to_translate).extend(["N"] * ((3 - len(tx_seq_to_translate) % 3) % 3)))

                tx_seq_cds = Seq(tx_seq_to_translate)
                protein_seq = str(tx_seq_cds.translate())

                if pro_ac is None:
                    # get_acs... will always return at least the MD5_ accession
                    pro_ac = (hdp.get_pro_ac_for_tx_ac(tx_ac) or hdp.get_acs_for_protein_seq(protein_seq)[0])

                transcript_data = RefTranscriptData(tx_seq, protein_seq, cds_start, cds_stop, pro_ac)

                return transcript_data

        if not (var_c.type == "c"):
            raise HGVSInvalidVariantError("Expected a cDNA (c.); got " + str(var_c))

        reference_data = RefTranscriptData.setup_transcript_data(self.hdp, var_c.ac, pro_ac)
        builder = altseqbuilder.AltSeqBuilder(var_c, reference_data)

        # TODO: handle case where you get 2+ alt sequences back;
        # currently get list of 1 element loop structure implemented
        # to handle this, but doesn't really do anything currently.
        all_alt_data = builder.build_altseq()

        var_ps = []
        for alt_data in all_alt_data:
            builder = altseq_to_hgvsp.AltSeqToHgvsp(reference_data, alt_data)
            var_p = builder.build_hgvsp()
            var_ps.append(var_p)

        var_p = var_ps[0]

        return var_p

    ############################################################################
    # Internal methods

    def _replace_reference(self, var):
        """fetch reference sequence for variant and update (in-place) if necessary"""

        if var.type not in "cgmnr":
            raise HGVSUnsupportedOperationError("Can only update references for type c, g, m, n, r")

        if var.posedit.edit.type == "ins":
            # insertions have no reference sequence (zero-width), so return as-is
            return var
        if var.posedit.edit.type == "con":
            # conversions have no reference sequence (zero-width), so return as-is
            return var

        pos = var.posedit.pos
        if ((isinstance(pos.start, hgvs.location.BaseOffsetPosition) and pos.start.offset != 0) or
            (isinstance(pos.end, hgvs.location.BaseOffsetPosition) and pos.end.offset != 0)):
            _logger.info("Can't update reference sequence for intronic variant {}".format(var))
            return var

        # For c. variants, we need coords on underlying sequences
        if var.type == "c":
            tm = self._fetch_TranscriptMapper(tx_ac=var.ac, alt_ac=var.ac, alt_aln_method="transcript")
            pos = tm.c_to_n(var.posedit.pos)
        else:
            pos = var.posedit.pos
        seq = self.hdp.get_seq(var.ac, pos.start.base - 1, pos.end.base)

        edit = var.posedit.edit
        if edit.ref != seq:
            _logger.debug("Replaced reference sequence in {var} with {seq}".format(var=var, seq=seq))
            edit.ref = seq

        return var

    @lru_cache(maxsize=hgvs.global_config.lru_cache.maxsize)
    def _fetch_TranscriptMapper(self, tx_ac, alt_ac, alt_aln_method):
        """
        Get a new TranscriptMapper for the given transcript accession (ac),
        possibly caching the result.
        """
        return hgvs.transcriptmapper.TranscriptMapper(self.hdp,
                                                      tx_ac=tx_ac,
                                                      alt_ac=alt_ac,
                                                      alt_aln_method=alt_aln_method)

    @staticmethod
    def _convert_edit_check_strand(strand, edit_in):
        """
        Convert an edit from one type to another, based on the stand and type
        """
        if isinstance(edit_in, hgvs.edit.NARefAlt):
            if strand == 1:
                edit_out = copy.deepcopy(edit_in)
            else:
                try:
                    # if smells like an int, do nothing
                    # TODO: should use ref_n, right?
                    int(edit_in.ref)
                    ref = edit_in.ref
                except (ValueError, TypeError):
                    ref = reverse_complement(edit_in.ref)
                edit_out = hgvs.edit.NARefAlt(ref=ref, alt=reverse_complement(edit_in.alt), )
        elif isinstance(edit_in, hgvs.edit.Dup):
            if strand == 1:
                edit_out = copy.deepcopy(edit_in)
            else:
                edit_out = hgvs.edit.Dup(ref=reverse_complement(edit_in.ref))
        elif isinstance(edit_in, hgvs.edit.Inv):
            if strand == 1:
                edit_out = copy.deepcopy(edit_in)
            else:
                try:
                    int(edit_in.ref)
                    ref = edit_in.ref
                except (ValueError, TypeError):
                    ref = reverse_complement(edit_in.ref)
                edit_out = hgvs.edit.Inv(ref=ref)
        else:
            raise NotImplementedError("Only NARefAlt/Dup/Inv types are currently implemented")
        return edit_out


class EasyVariantMapper(VariantMapper):
    """Provides simplified variant mapping for a single assembly and
    transcript-reference alignment method.

    EasyVariantMapper is instantiated with an assembly name and
    alt_aln_method. These enable the following conveniences over
    VariantMapper:

    * The assembly and alignment method are used to
      automatically select an appropriate chromosomal reference
      sequence when mapping from a transcript to a genome (i.e.,
      c_to_g(...) and n_to_g(...)).

    * A new method, relevant_trancripts(g_variant), returns a list of
      transcript accessions available for the specified variant. These
      accessions are candidates mapping from genomic to trancript
      coordinates (i.e., g_to_c(...) and g_to_n(...)).

    IMPORTANT: Callers should be prepared to catch HGVSError
    exceptions. These will be thrown whenever a transcript maps
    ambiguously to a chromosome, such as for pseudoautosomal region
    transcripts.

    """

    def __init__(self,
                 hdp,
                 assembly_name=hgvs.global_config.mapping.assembly,
                 alt_aln_method=hgvs.global_config.mapping.alt_aln_method,
                 normalize=hgvs.global_config.mapping.normalize,
                 in_par_assume=hgvs.global_config.mapping.in_par_assume,
                 replace_reference=hgvs.global_config.mapping.replace_reference,
                 *args, **kwargs
                 ):
        """
        :param object hdp: instance of hgvs.dataprovider subclass
        :param bool replace_reference: replace reference (entails additional network access)

        :param str assembly_name: name of assembly ("GRCh38.p5")
        :param str alt_aln_method: genome-transcript alignment method ("splign", "blat", "genewise")
        :param bool normalize: normalize variants
        :param str in_par_assume: during x_to_g, assume this chromosome name if alignment is ambiguous

        :raises HGVSError subclasses: for a variety of mapping and data lookup failures
        """

        super(EasyVariantMapper, self).__init__(hdp=hdp,
                                                replace_reference=replace_reference,
                                                *args, **kwargs)
        self.assembly_name = assembly_name
        self.alt_aln_method = alt_aln_method
        self.normalize = normalize
        self.in_par_assume = in_par_assume
        self._norm = None
        if self.normalize:
            self._norm = hgvs.normalizer.Normalizer(hdp, alt_aln_method=alt_aln_method, validate=False)
        self._validator = hgvs.validator.IntrinsicValidator()
        self._assembly_map = hdp.get_assembly_map(self.assembly_name)
        self._assembly_accessions = set(self._assembly_map.keys())

    def __repr__(self):
        return ("{self.__module__}.{t.__name__}(alt_aln_method={self.alt_aln_method}, "
                "assembly_name={self.assembly_name}, normalize={self.normalize}, "
                "replace_reference={self.replace_reference})".format(
                    self=self, t=type(self)))

    def g_to_c(self, var_g, tx_ac):
        self._validator.validate(var_g)
        var_out = super(EasyVariantMapper, self).g_to_c(var_g, tx_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def g_to_n(self, var_g, tx_ac):
        self._validator.validate(var_g)
        var_out = super(EasyVariantMapper, self).g_to_n(var_g, tx_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def g_to_t(self, var_g, tx_ac):
        self._validator.validate(var_g)
        var_out = super(EasyVariantMapper, self).g_to_t(var_g, tx_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def c_to_g(self, var_c):
        self._validator.validate(var_c)
        alt_ac = self._alt_ac_for_tx_ac(var_c.ac)
        var_out = super(EasyVariantMapper, self).c_to_g(var_c, alt_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def n_to_g(self, var_n):
        self._validator.validate(var_n)
        alt_ac = self._alt_ac_for_tx_ac(var_n.ac)
        var_out = super(EasyVariantMapper, self).n_to_g(var_n, alt_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def t_to_g(self, var_t):
        self._validator.validate(var_t)
        alt_ac = self._alt_ac_for_tx_ac(var_t.ac)
        var_out = super(EasyVariantMapper, self).t_to_g(var_t, alt_ac, alt_aln_method=self.alt_aln_method)
        return self._maybe_normalize(var_out)

    def c_to_n(self, var_c):
        self._validator.validate(var_c)
        var_out = super(EasyVariantMapper, self).c_to_n(var_c)
        return self._maybe_normalize(var_out)

    def n_to_c(self, var_n):
        self._validator.validate(var_n)
        var_out = super(EasyVariantMapper, self).n_to_c(var_n)
        return self._maybe_normalize(var_out)

    def c_to_p(self, var_c):
        self._validator.validate(var_c)
        var_out = super(EasyVariantMapper, self).c_to_p(var_c)
        return self._maybe_normalize(var_out)

    def relevant_transcripts(self, var_g):
        """return list of transcripts accessions (strings) for given variant,
        selected by genomic overlap"""
        self._validator.validate(var_g)
        tx = self.hdp.get_tx_for_region(var_g.ac, self.alt_aln_method, var_g.posedit.pos.start.base,
                                        var_g.posedit.pos.end.base)
        return [e["tx_ac"] for e in tx]

    def _alt_ac_for_tx_ac(self, tx_ac):
        """return chromosomal accession for given transcript accession (and
        the_assembly and aln_method setting used to instantiate this
        EasyVariantMapper)

        """
        alt_acs = [e["alt_ac"]
                   for e in self.hdp.get_tx_mapping_options(tx_ac)
                   if e["alt_aln_method"] == self.alt_aln_method and e["alt_ac"] in self._assembly_accessions]

        if len(alt_acs) == 0:
            raise HGVSDataNotAvailableError(
                "No alignments for {tx_ac} in {an} using {am}".format(tx_ac=tx_ac,
                                                                      an=self.assembly_name,
                                                                      am=self.alt_aln_method))

        if len(alt_acs) > 1:
            names = set(self._assembly_map[ac] for ac in alt_acs)
            if names != set("XY"):
                raise HGVSError("Multiple chromosomal alignments for {tx_ac} in {an}"
                                " using {am} (non-pseudoautosomal region, paralogs)".format(
                                    tx_ac=tx_ac, an=self.assembly_name, am=self.alt_aln_method))

            # assume PAR
            if self.in_par_assume is None:
                raise HGVSError("Multiple chromosomal alignments for {tx_ac} in {an}"
                                " using {am} (likely pseudoautosomal region)".format(
                                    tx_ac=tx_ac, an=self.assembly_name, am=self.alt_aln_method))

            alt_acs = [ac for ac in alt_acs if self._assembly_map[ac] == self.in_par_assume]
            if len(alt_acs) != 1:
                raise HGVSError("Multiple chromosomal alignments for {tx_ac} in {an}"
                                " using {am}; in_par_assume={ipa} selected {n} of them".format(
                                    tx_ac=tx_ac, an=self.assembly_name, am=self.alt_aln_method,
                                    ipa=self.in_par_assume, n=len(alt_acs)))

        assert len(alt_acs) == 1, "Should have exactly one alignment at this point"
        return alt_acs[0]

    def _maybe_normalize(self, var):
        """normalize variant if requested, and ignore HGVSUnsupportedOperationError
        This is better than checking whether the variant is intronic because
        future UTAs will support LRG, which will enable checking intronic variants.
        """
        if self._norm is not None:
            try:
                return self._norm.normalize(var)
            except HGVSUnsupportedOperationError as e:
                _logger.warn(str(e) + "; returning unnormalized variant")
                # fall through to return unnormalized variant
        return var

# <LICENSE>
# Copyright 2013-2015 HGVS Contributors (https://bitbucket.org/biocommons/hgvs)
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# </LICENSE>
