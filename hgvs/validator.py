# -*- coding: utf-8 -*-
"""implements validation of hgvs variants

"""

from __future__ import absolute_import, division, print_function, unicode_literals

from hgvs.exceptions import HGVSInvalidVariantError, HGVSUnsupportedOperationError
import hgvs.parser
import hgvs.edit
import hgvs.variantmapper

BASE_RANGE_ERROR_MSG = "base start position must be <= end position"
INS_ERROR_MSG = "insertion length must be 1"
DEL_ERROR_MSG = "Length implied by coordinates ({span_len}) must equal sequence deletion length ({del_len})"
AC_ERROR_MSG = "Accession is not present in BDI database"
SEQ_ERROR_MSG = "Variant reference ({var_ref_seq}) does not agree with reference sequence ({ref_seq})"

BASE_OFFSET_COORD_TYPES = "cnr"
SIMPLE_COORD_TYPES = "gmp"


class Validator(object):
    """invoke intrinsic and extrinsic validation"""

    def __init__(self, hdp):
        self._ivr = IntrinsicValidator()
        self._evr = ExtrinsicValidator(hdp)

    def validate(self, var):
        return self._ivr.validate(var) and self._evr.validate(var)


class IntrinsicValidator(object):
    """
    Attempts to determine if the HGVS name is internally consistent

    """

    def validate(self, var):
        assert isinstance(var, hgvs.variant.SequenceVariant), "variant must be a parsed HGVS sequence variant object"
        self._start_lte_end(var)
        self._ins_length_is_one(var)
        self._del_length(var)
        return True

    def _start_lte_end(self, var):
        if not var.posedit.pos or not var.posedit.pos.start or not var.posedit.pos.end:
            return True
        if var.type == 'p':
            return True
        if var.posedit.pos.start <= var.posedit.pos.end:
            return True
        else:
            raise HGVSInvalidVariantError(BASE_RANGE_ERROR_MSG)

    def _ins_length_is_one(self, var):
        if not var.posedit.pos or not var.posedit.pos.start or not var.posedit.pos.end:
            return True
        if not isinstance(var.posedit.edit, hgvs.edit.NARefAlt) and not isinstance(var.posedit.edit, hgvs.edit.AARefAlt):
            return True
        if var.posedit.edit.type == "ins":
            if var.type in SIMPLE_COORD_TYPES:
                if (var.posedit.pos.end.base - var.posedit.pos.start.base) != 1:
                    raise HGVSInvalidVariantError(INS_ERROR_MSG)
            if var.type in BASE_OFFSET_COORD_TYPES:
                if var.posedit.pos.start.datum == var.posedit.pos.end.datum:
                    if ((var.posedit.pos.end.base + var.posedit.pos.end.offset) -
                        (var.posedit.pos.start.base + var.posedit.pos.start.offset)) != 1:
                        raise HGVSInvalidVariantError(INS_ERROR_MSG)
            return True

    def _del_length(self, var):
        if not isinstance(var.posedit.edit, hgvs.edit.NARefAlt) and not isinstance(var.posedit.edit, hgvs.edit.AARefAlt):
            return True
        if var.posedit.edit.type in ["del", "delins"]:
            ref_len = var.posedit.edit.ref_n
            if ref_len is None:
                return True

            if var.type in BASE_OFFSET_COORD_TYPES:
                if var.posedit.pos.start.datum != hgvs.location.CDS_END and var.posedit.pos.end.datum == hgvs.location.CDS_END:
                    raise HGVSUnsupportedOperationError(
                        "Validating deletion length across CDS end is unsupported ({}); consider projecting to n. first".format(str(var)))
                if not ((var.posedit.pos.start.offset == var.posedit.pos.end.offset == 0) or
                        (var.posedit.pos.start.base == var.posedit.pos.end.base)):
                    raise HGVSUnsupportedOperationError(
                        "Validating deletion length for variants across exon/intron junctions is unsupported ({})".format(str(var)))
                span_len = ((var.posedit.pos.end.base + var.posedit.pos.end.offset) -
                            (var.posedit.pos.start.base + var.posedit.pos.start.offset) + 1)
                # BO numbering is missing 0 (... -2 -1, 1, 2 ...) ⇒ adjust length if crossing
                if var.posedit.pos.start.base < 0 and var.posedit.pos.end.base > 0:
                    span_len -= 1
            else:
                span_len = var.posedit.pos.end.base - var.posedit.pos.start.base + 1

            if span_len != ref_len:
                raise HGVSInvalidVariantError(DEL_ERROR_MSG.format(span_len=span_len, del_len=ref_len))
        return True


class ExtrinsicValidator():
    """
    Attempts to determine if the HGVS name validates against external data sources
    """

    def __init__(self, hdp):
        self.hdp = hdp
        self.vm = hgvs.variantmapper.VariantMapper(self.hdp)

    def validate(self, var):
        assert isinstance(var, hgvs.variant.SequenceVariant), "variant must be a parsed HGVS sequence variant object"
        self._ref_is_valid(var)
        return True

    def _ref_is_valid(self, var):
        # use reference sequence of original variant, even if later converted (eg c_to_n)
        if (var.type in BASE_OFFSET_COORD_TYPES and var.posedit.pos is not None and
            (var.posedit.pos.start.offset != 0 or var.posedit.pos.end.offset != 0)):
            raise HGVSUnsupportedOperationError("Cannot validate sequence of an intronic variant ({})".format(str(var)))

        ref_checks = []
        if var.type == 'p':
            if not var.posedit.pos or not var.posedit.pos.start or not var.posedit.pos.end:
                return True
            ref_checks.append( (var.ac, var.posedit.pos.start.pos, var.posedit.pos.start.pos, var.posedit.pos.start.aa) )
            if var.posedit.pos.start.pos != var.posedit.pos.end.pos:
                ref_checks.append( (var.ac, var.posedit.pos.end.pos, var.posedit.pos.end.pos, var.posedit.pos.end.aa) )
        else:
            var_ref_seq = getattr(var.posedit.edit, "ref", None) or None
            var_x = self.vm.c_to_n(var) if var.type == "c" else var
            ref_checks.append( (var_x.ac, var_x.posedit.pos.start.base, var_x.posedit.pos.end.base, var_ref_seq) )

        for ac, var_ref_start, var_ref_end, var_ref_seq in ref_checks:
            if var_ref_start is None or var_ref_end is None or not var_ref_seq:
                continue

            # ref_seq is digit, as in "del6"
            try:
                int(var_ref_seq)
                continue
            except ValueError:
                pass

            ref_seq = self.hdp.get_seq(ac, var_ref_start - 1, var_ref_end)
            if ref_seq != var_ref_seq:
                raise HGVSInvalidVariantError(str(var) + ": " + SEQ_ERROR_MSG.format(ref_seq=ref_seq,
                                                                                 var_ref_seq=var_ref_seq))

        return True

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
