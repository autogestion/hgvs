# -*- coding: utf-8 -*-
"""Representation of edit operations in HGVS variants

NARefAlt and AARefAlt are abstractions of several major variant
types.  They are distinguished by whether the ref and alt elements
of the structure.  The HGVS grammar for NA and AA are subtly
different (e.g., the ref AA in a protein substitution is part of the
location).

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import recordtype

from bioutils.sequences import aa_to_aa1, aa1_to_aa3

import hgvs
from hgvs.exceptions import HGVSError, HGVSUnsupportedOperationError


class Edit(object):
    def format(self, conf=None):
        return str(self)

    def _format_config(self, conf=None):
        p_3_letter = hgvs.global_config.formatting.p_3_letter
        p_term_asterisk = hgvs.global_config.formatting.p_term_asterisk
        if conf and "p_3_letter" in conf and conf["p_3_letter"] is not None:
            p_3_letter = conf["p_3_letter"]
        if conf and "p_term_asterisk" in conf and conf["p_term_asterisk"] is not None:
            p_term_asterisk = conf["p_term_asterisk"]
        return p_3_letter, p_term_asterisk

    def _del_ins_lengths(self, ilen):
        raise HGVSUnsupportedOperationError("internal function _del_ins_lengths not implemented for this variant type")


class NARefAlt(Edit, recordtype.recordtype("NARefAlt", [("ref", None), ("alt", None), ("uncertain", False)])):
    """
    represents substitutions, deletions, insertions, and indels.

    :ivar ref: reference sequence or length
    :ivar alt: alternate sequence
    :ivar uncertain: boolean indicating whether the variant is uncertain/undetermined
    """

    def __init__(self, ref=None, alt=None, uncertain=False, edit=None):
        if edit:
            ref = edit.ref
            alt = edit.alt
            uncertain = edit.uncertain
        super(NARefAlt, self).__init__(ref=ref, alt=alt, uncertain=uncertain)

    @property
    def ref_s(self):
        """
        returns a string representing the ref sequence, if it is not None and smells like a sequence

        >>> NARefAlt("ACGT").ref_s
        u'ACGT'
        >>> NARefAlt("7").ref_s
        >>> NARefAlt(7).ref_s

        """
        return self.ref if (isinstance(self.ref, basestring) and self.ref and self.ref[0] in "ACGTUN") else None

    @property
    def ref_n(self):
        """
        returns an integer, either from the `ref` instance variable if it's a number, or the length of
        ref if it's a string, or None otherwise

        >>> NARefAlt("ACGT").ref_n
        4
        >>> NARefAlt("7").ref_n
        7
        >>> NARefAlt(7).ref_n
        7

        """
        try:
            return int(self.ref)
        except ValueError:
            return len(self.ref) if self.ref else None

    def __str__(self):
        if self.ref is None and self.alt is None:
            raise HGVSError("RefAlt: ref and alt sequences are both undefined")

        # subst and delins
        if self.ref is not None and self.alt is not None:
            if self.ref == self.alt:
                s = "{self.ref}=".format(self=self)
            elif len(self.alt) == 1 and len(self.ref) == 1 and not self.ref.isdigit():    # don't turn del5insT into 5>T
                s = "{self.ref}>{self.alt}".format(self=self)
            else:
                s = "del{self.ref}ins{self.alt}".format(self=self)
        # del case
        elif self.ref is not None:
            s = "del{self.ref}".format(self=self)

        # ins case
        else:    # self.alt is not None
            s = "ins{self.alt}".format(self=self)

        return "(" + s + ")" if self.uncertain else s

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        if self.ref is not None and self.alt is not None:
            if self.ref == self.alt:
                edit_type = "identity"
            elif len(self.alt) == 1 and len(self.ref) == 1 and not self.ref.isdigit():
                edit_type = "sub"
            else:
                edit_type = "delins"
        elif self.ref is not None:
            edit_type = "del"
        else:
            edit_type = "ins"
        return edit_type


    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        del_len = 0 if self.ref is None else ilen
        ins_len = 0 if self.alt is None else len(self.alt)
        return (del_len, ins_len)


class AARefAlt(Edit, recordtype.recordtype("AARefAlt", [("ref", None), ("alt", None), ("uncertain", False)])):
    def __init__(self, ref, alt, uncertain=False):
        super(AARefAlt, self).__init__(ref=aa_to_aa1(ref), alt=aa_to_aa1(alt), uncertain=uncertain)

    def format(self, conf=None):
        if self.ref is None and self.alt is None:
            # raise HGVSError("RefAlt: ref and alt sequences are both undefined")
            return "="

        p_3_letter, p_term_asterisk = self._format_config(conf)
        
        # subst and delins
        if self.ref is not None and self.alt is not None:
            if self.ref == self.alt:
                if p_3_letter:
                    s = "{ref}=".format(ref=aa1_to_aa3(self.ref))
                    if p_term_asterisk and s == "Ter=":
                        s = "*="
                else:
                    s = "{ref}=".format(ref=self.ref)
            elif len(self.ref) == 1 and len(self.alt) == 1:
                if p_3_letter:
                    s = aa1_to_aa3(self.alt)
                    if p_term_asterisk and s == "Ter":
                        s = "*"
                else:
                    s = self.alt
            else:
                if p_3_letter:
                    s = "delins{alt}".format(alt=aa1_to_aa3(self.alt))
                    if p_term_asterisk and s == "delinsTer":
                        s = "delins*"
                else:
                    s = "delins{alt}".format(alt=self.alt)

        # del case
        elif self.ref is not None and self.alt is None:
            s = "del"

        # ins case
        elif self.ref is None and self.alt is not None:
            if p_3_letter:
                s = "ins{alt}".format(alt=aa1_to_aa3(self.alt))
                if p_term_asterisk and s == "insTer":
                    s = "ins*"
            else:
                s = "ins{alt}".format(alt=self.alt)

        else:
            raise RuntimeError("Should not be here")

        return "(" + s + ")" if self.uncertain else s

    __str__ = format

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        if self.ref is not None and self.alt is not None:
            if self.ref == self.alt:
                edit_type = "identity"
            elif len(self.ref) == 1 and len(self.alt) == 1:
                edit_type = "sub"
            else:
                edit_type = "delins"
        elif self.ref is not None and self.alt is None:
            edit_type = "del"
        elif self.ref is None and self.alt is not None:
            edit_type = "ins"
        return edit_type

    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        del_len = 0 if (self.ref is None or self.alt == "") else ilen
        ins_len = 0 if self.alt is None else len(self.alt)
        return (del_len, ins_len)


class AASub(AARefAlt):
    def format(self, conf=None):
        p_3_letter, p_term_asterisk = self._format_config(conf)
        
        if p_3_letter:
            s = aa1_to_aa3(self.alt) if self.alt != "?" else self.alt
            if p_term_asterisk and s == "Ter":
                s = "*"
        else:
            s = self.alt
        return "(" + s + ")" if self.uncertain else s

    __str__ = format

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "sub"


class AAFs(Edit, recordtype.recordtype("AAFs", [("ref", None), ("alt", None), ("length", None), ("uncertain", False)])):
    def __init__(self, ref, alt, length=None, uncertain=False):
        super(AAFs, self).__init__(ref=aa_to_aa1(ref), alt=aa_to_aa1(alt), length=length, uncertain=uncertain)

    def format(self, conf=None):
        p_3_letter, p_term_asterisk = self._format_config(conf)
        
        st_length = self.length or ""
        if p_3_letter:
            if p_term_asterisk:
                s = "{alt}fs*{length}".format(alt=aa1_to_aa3(self.alt), length=st_length)
            else:
                s = "{alt}fsTer{length}".format(alt=aa1_to_aa3(self.alt), length=st_length)
        else:
            s = "{alt}fs*{length}".format(alt=self.alt, length=st_length)
        return "(" + s + ")" if self.uncertain else s

    __str__ = format

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "fs"


class AAExt(Edit, recordtype.recordtype("AAExt", [("ref", None), ("alt", None), ("aaterm", None), ("length", None),
                                                  ("uncertain", False)])):
    def __init__(self, ref, alt, aaterm=None, length=None, uncertain=False):
        super(AAExt, self).__init__(ref=aa_to_aa1(ref),
                                    alt=aa_to_aa1(alt),
                                    aaterm=aa_to_aa1(aaterm),
                                    length=length,
                                    uncertain=uncertain)

    def format(self, conf=None):
        p_3_letter, p_term_asterisk = self._format_config(conf)
        
        st_alt = self.alt or ""
        st_aaterm = self.aaterm or ""
        st_length = self.length or ""
        if p_3_letter:
            st_alt = aa1_to_aa3(st_alt)
            st_aaterm = aa1_to_aa3(st_aaterm)
            if p_term_asterisk and st_alt == "Ter":
                st_alt = "*"
            if p_term_asterisk and st_aaterm == "Ter":
                st_aaterm = "*"
                
        s = "{alt}ext{term}{length}".format(alt=st_alt, term=st_aaterm, length=st_length)
        return "(" + s + ")" if self.uncertain else s

    __str__ = format

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "ext"

    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        return (0, abs(self.length))



class Dup(Edit, recordtype.recordtype('Dup', [('ref', None), ('uncertain', False)])):
    def __init__(self, ref=None, uncertain=False, edit=None):
        if edit:
            ref = edit.ref
            uncertain = edit.uncertain
        super(Dup, self).__init__(ref=ref, uncertain=uncertain)

    def __str__(self):
        return "dup" + (self.ref or "")

    @property
    def ref_s(self):
        """
        returns a string representing the ref sequence, if it is not None and smells like a sequence
        """
        return self.ref if (isinstance(self.ref, basestring) and self.ref and self.ref[0] in "ACGTUN") else None

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "dup"

    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        if self.ref is not None and self.ref != "":
            assert len(self.ref) == ilen
        return (0, ilen)



class Repeat(Edit, recordtype.recordtype('Repeat', [('ref', None), ('min', None), ('max', None),
                                                    ('uncertain', False)])):
    def __str__(self):
        if self.min > self.max:
            raise HGVSError("Repeat min count must be less than or equal to max count")
        if self.min == self.max:
            return "{self.ref}[{self.min}]".format(self=self)
        return "{self.ref}({self.min}_{self.max})".format(self=self)

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "repeat"



class NACopy(Edit, recordtype.recordtype("NACopy", ["copy", ("uncertain", False)])):
    """Represent copy number variants (Invitae-specific use)

    This class is intended for Invitae use only and does not represent
    a standard HGVS concept. The class may be changed, moved, or
    removed without notice.

    """

    def __str__(self):
        s = "copy{}".format(self.copy)
        return "(" + s + ")" if self.uncertain else s

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "copy"

    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        return (0, ilen * self.copy)



class Inv(Edit, recordtype.recordtype('Inv', [('ref', None), ('uncertain', False)])):
    """Inversion
    """

    def __init__(self, ref=None, uncertain=False, edit=None):
        if edit:
            ref = edit.ref
            uncertain = edit.uncertain
        super(Inv, self).__init__(ref=ref, uncertain=uncertain)

    def __str__(self):
        return "inv"

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def ref_s(self):
        return self.ref if (isinstance(self.ref, basestring) and self.ref and self.ref[0] in "ACGTUN") else None

    @property
    def ref_n(self):
        """
        returns an integer, either from the `seq` instance variable if it's a number,
        or None otherwise
        """
        try:
            return int(self.ref)
        except ValueError:
            return None

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "inv"

    def _del_ins_lengths(self, ilen):
        """returns (del_len, ins_len).
        Unspecified ref or alt returns None for del_len or ins_len respectively.
        """
        return (ilen, ilen)


class Conv(Edit, recordtype.recordtype('Conv', [('from_ac', None), ('from_type', None), ('from_pos', None),
                                                ('uncertain', False)])):
    """Conversion
    """

    def __init__(self, from_ac=None, from_type=None, from_pos=None, uncertain=False, edit=None):
        if edit:
            from_ac = edit.from_ac
            from_type = edit.from_type
            from_pos = edit.from_pos
            uncertain = edit.uncertain
        super(Conv, self).__init__(from_ac=from_ac, from_type=from_type, from_pos=from_pos, uncertain=uncertain)

    def __str__(self):
        if self.from_ac and self.from_type and self.from_pos:
            s = "con{self.from_ac}:{self.from_type}.{self.from_pos}".format(self=self)
        else:
            s = "con"
        return "(" + s + ")" if self.uncertain else s

    def _set_uncertain(self):
        """sets the uncertain flag to True; used primarily by the HGVS grammar

        :returns: self
        """
        self.uncertain = True
        return self

    @property
    def type(self):
        """return the type of this Edit

        :returns: edit type (str)
        """
        return "con"


if __name__ == "__main__":
    import doctest
    doctest.testmod()

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
