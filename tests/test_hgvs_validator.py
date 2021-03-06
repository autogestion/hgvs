# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

from nose.plugins.attrib import attr

from hgvs.exceptions import HGVSInvalidVariantError, HGVSUnsupportedOperationError
import hgvs.dataproviders.uta
import hgvs.variantmapper
import hgvs.parser
import hgvs.validator

hdp = hgvs.dataproviders.uta.connect(mode="run", cache="tests/data/cache.hdp")


class Test_HGVSValidator(unittest.TestCase):
    """Validator wrapper class tests (most testing is handled by the component classes)"""

    @classmethod
    def setUp(cls):
        cls.hp = hgvs.parser.Parser()
        cls.vr = hgvs.validator.Validator(hdp)

    def test_wrapper(self):
        """Test that validator wrapper is working"""
        self.assertTrue(self.vr.validate(self.hp.parse_hgvs_variant("NM_001005405.2:c.6C>A")))
        self.assertTrue(self.vr.validate(self.hp.parse_hgvs_variant("NP_000305.3:p.?")))


@attr(tags=["quick", "validation"])
class Test_HGVSIntrinsicValidator(unittest.TestCase):
    """Tests for internal validation"""

    @classmethod
    def setUpClass(cls):
        cls.hp = hgvs.parser.Parser()
        cls.validate_int = hgvs.validator.IntrinsicValidator()

    def test_start_lte_end(self):
        """Test if start position is less <= end position"""
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NC_000007.13:g.36561662C>T")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NC_000007.13:g.36561662_36561663insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NM_01234.5:c.76_77insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+54_123+55insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+54A>T")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NC_012920.1:m.54G>C")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NC_012920.1:m.57_58insC")))

        with self.assertRaisesRegexp(HGVSInvalidVariantError, hgvs.validator.BASE_RANGE_ERROR_MSG):
            self.validate_int.validate(self.hp.parse_hgvs_variant("NC_000007.13:g.36561664_36561663A>T"))

        with self.assertRaisesRegexp(HGVSInvalidVariantError, hgvs.validator.BASE_RANGE_ERROR_MSG):
            self.validate_int.validate(self.hp.parse_hgvs_variant("NM_000277.1:c.3_1delAG"))

        with self.assertRaisesRegexp(HGVSInvalidVariantError, hgvs.validator.BASE_RANGE_ERROR_MSG):
            self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+56_123+55A>T"))

    def test_ins_length_is_one(self):
        """Test if insertion length = 1"""
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("NC_000007.13:g.36561662_36561663insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.76_77insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+54_123+55insT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123-54_123-53insT")))

        with self.assertRaisesRegexp(HGVSInvalidVariantError, hgvs.validator.INS_ERROR_MSG):
            self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.76_78insTT"))

        with self.assertRaisesRegexp(HGVSInvalidVariantError, hgvs.validator.INS_ERROR_MSG):
            self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+54_123+56insT"))

    def test_del_length(self):
        """Test if del length agrees with position range"""
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.76_78delACT")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.123+54_123+55delTA")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.76_78del")))
        self.assertTrue(self.validate_int.validate(self.hp.parse_hgvs_variant('NM_003060.3:c.-91_22del113')))

        with self.assertRaises(HGVSInvalidVariantError):
            self.validate_int.validate(self.hp.parse_hgvs_variant("AC_01234.5:c.76_78delACTACAT"))
        with self.assertRaises(HGVSUnsupportedOperationError):
            self.validate_int.validate(self.hp.parse_hgvs_variant("NM_000030.2:c.679_680+2delAAGT"))
        with self.assertRaises(HGVSUnsupportedOperationError):
            self.validate_int.validate(self.hp.parse_hgvs_variant("NM_032487.4:c.831_*2687del2976"))


@attr(tags=["validation"])
class Test_HGVSExtrinsicValidator(unittest.TestCase):
    """Tests for external validation"""

    @classmethod
    def setUpClass(cls):
        cls.hp = hgvs.parser.Parser()
        cls.validate_ext = hgvs.validator.ExtrinsicValidator(hdp)

    def test_valid_ref(self):
        """Test variants with valid reference seqeuences."""
        hgvs_variants = ["NM_001005405.2:c.6C>A",
                         "NM_001005405.2:c.-38T>A",
                         "NM_001005405.2:c.*3C>G",
                         "NM_001005405.2:c.435_440delCTGCTG",
                         "NM_000187.3:c.457dupG",
                         "NR_002728.3:r.55A>U",
                         "NM_000495.3:c.610_628del19",
                         "NM_000059.3:c.44_45insATT",
                         "NC_000001.10:g.156104193G>A",
                         "NP_000010.1:p.Asn158Ser",
                         "NP_000042.3:p.His1082_Val1085delinsLeuHisGlnAla",
                         "NP_000042.3:p.His1082ArgfsTer2",
                         ]
        for var in [self.hp.parse_hgvs_variant(h) for h in hgvs_variants]:
            self.assertTrue(self.validate_ext.validate(var))

    def test_invalid_ref(self):
        """Test variants with invalid reference sequences."""
        hgvs_variants = ["NM_001005405.2:c.435_440delCTGCT",
                         "NR_002728.3:r.55C>U",
                         "NC_000001.10:g.156104193C>A",
                         "NP_000010.1:p.Ser158Arg",
                         "NP_000042.3:p.Arg1082_Val1085delinsLeuHisGlnAla",
                         "NP_000042.3:p.His1082_Arg1085delinsLeuHisGlnAla",
                         "NP_000042.3:p.Ser1082ArgfsTer2",
                         ]

        for var in [self.hp.parse_hgvs_variant(h) for h in hgvs_variants]:
            with self.assertRaises(HGVSInvalidVariantError):
                self.validate_ext.validate(var)


if __name__ == "__main__":
    unittest.main()

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
