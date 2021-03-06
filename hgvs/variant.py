# -*- coding: utf-8 -*-
"""represents simple sequence-based variants

"""

from __future__ import absolute_import, division, print_function, unicode_literals

import recordtype

import hgvs.variantmapper


class SequenceVariant(recordtype.recordtype("SequenceVariant", ["ac", "type", "posedit"])):
    """
    represents a basic HGVS variant.  The only requirement is that each
    component can be stringified; for example, passing pos as either a string
    or an hgvs.location.CDSInterval (for example) are both intended uses
    """

    def format(self, conf=None):
        """Formatting the stringification of sequence variants

        :param conf: a dict comprises formatting options. None is to use global settings.
        formatting configuration options:
            p_3_letter: use 1-letter or 3-letter amino acid representation for p. variants.
            p_term_asterisk: use * or Ter to represent stop-codon gain for p. variants.
        """
        if self.ac is not None:
            return "{ac}:{type}.{posedit}".format(ac=self.ac, type=self.type, posedit=self.posedit.format(conf))
        else:
            return "{type}.{posedit}".format(type=self.type, posedit=self.posedit.format(conf))

    __str__ = format

    def fill_ref(self, hdp):
        hm = hgvs.variantmapper.VariantMapper(hdp)
        type = self.posedit.edit.type
        if type in ["del", "delins", "identity", "dup", "inv"] and self.posedit.edit.ref_s is None:
            hm._replace_reference(self)
        if type == "identity" and isinstance(self.posedit.edit, hgvs.edit.NARefAlt):
            self.posedit.edit.alt = self.posedit.edit.ref
        return self


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
