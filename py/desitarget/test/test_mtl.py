# Licensed under a 3-clause BSD style license - see LICENSE.rst
# -*- coding: utf-8 -*-
"""Test desitarget.mtl.
"""
import os
import unittest
import numpy as np
from astropy.table import Table, join

from desitarget.targetmask import desi_mask as Mx
from desitarget.sv1.sv1_targetmask import desi_mask as MxSV
from desitarget.targetmask import obsconditions
from desitarget.mtl import make_mtl
from desitarget.targets import initial_priority_numobs, main_cmx_or_sv


class TestMTL(unittest.TestCase):

    def setUp(self):
        self.targets = Table()
        self.types = np.array(['ELG', 'LRG', 'QSO', 'QSO', 'ELG'])
        self.priorities = [Mx[t].priorities['UNOBS'] for t in self.types]
        self.post_prio = [Mx[t].priorities['MORE_ZGOOD'] for t in self.types]
        self.post_prio[0] = 2  # ELG
        self.post_prio[1] = 2  # LRG...all one-pass
        self.post_prio[2] = 2  # lowz QSO
        self.targets['DESI_TARGET'] = [Mx[t].mask for t in self.types]
        self.targets['BGS_TARGET'] = np.zeros(len(self.types), dtype=np.int64)
        self.targets['MWS_TARGET'] = np.zeros(len(self.types), dtype=np.int64)
        n = len(self.targets)
        self.targets['ZFLUX'] = 10**((22.5-np.linspace(20, 22, n))/2.5)
        self.targets['TARGETID'] = list(range(n))
        # ADM determine the initial PRIORITY and NUMOBS.
        pinit, ninit = initial_priority_numobs(self.targets)
        self.targets["PRIORITY_INIT"] = pinit
        self.targets["NUMOBS_INIT"] = ninit

        # - reverse the order for zcat to make sure joins work
        self.zcat = Table()
        self.zcat['TARGETID'] = self.targets['TARGETID'][-2::-1]
        self.zcat['Z'] = [2.5, 1.0, 0.5, 1.0]
        self.zcat['ZWARN'] = [0, 0, 0, 0]
        self.zcat['NUMOBS'] = [1, 1, 1, 1]
        self.zcat['SPECTYPE'] = ['QSO', 'QSO', 'GALAXY', 'GALAXY']

    def reset_targets(self, prefix):
        """Add prefix to TARGET columns"""

        t = self.targets.copy()
        main_names = ['DESI_TARGET', 'BGS_TARGET', 'MWS_TARGET']

        if prefix == 'CMX':
            # ADM restructure the table to look like a commissioning table.
            t.rename_column('DESI_TARGET', 'CMX_TARGET')
            t.remove_column('BGS_TARGET')
            t.remove_column('MWS_TARGET')
        else:
            for name in main_names:
                t.rename_column(name, prefix+name)

#        if prefix == "SV1_":
            # ADM change any occurences of LRG_2PASS to just LRG.
            # ADM technically not needed as 2PASS no longer exists.
#            ii = t["SV1_DESI_TARGET"] == Mx.LRG_2PASS
#            t["SV1_DESI_TARGET"][ii] = MxSV.LRG

        return t

    def test_mtl(self):
        """Test output from MTL has the correct column names.
        """
        # ADM loop through once each for the main survey, commissioning and SV.
        for prefix in ["", "CMX_", "SV1_"]:
            t = self.reset_targets(prefix)
            mtl = make_mtl(t, "BRIGHT|GRAY|DARK")
            goodkeys = sorted(set(t.dtype.names) | set(['NUMOBS_MORE', 'PRIORITY', 'OBSCONDITIONS']))
            mtlkeys = sorted(mtl.dtype.names)
            self.assertEqual(mtlkeys, goodkeys)

    def test_numobs(self):
        """Test priorities, numobs and obsconditions are set correctly with no zcat.
        """
        # ADM loop through once for SV and once for the main survey.
        for prefix in ["", "SV1_"]:
            t = self.reset_targets(prefix)
            mtl = make_mtl(t, "GRAY|DARK")
            mtl.sort(keys='TARGETID')
            self.assertTrue(np.all(mtl['NUMOBS_MORE'] == [1, 1, 4, 4, 1]))
            self.assertTrue(np.all(mtl['PRIORITY'] == self.priorities))
            # - Check that ELGs can be observed in gray conditions but not others
            iselg = (self.types == 'ELG')
            self.assertTrue(np.all((mtl['OBSCONDITIONS'][iselg] & obsconditions.GRAY) != 0))
            self.assertTrue(np.all((mtl['OBSCONDITIONS'][~iselg] & obsconditions.GRAY) == 0))

    def test_zcat(self):
        """Test priorities, numobs and obsconditions are set correctly after zcat.
        """
        # ADM loop through once for SV and once for the main survey.
        for prefix in ["", "SV1_"]:
            t = self.reset_targets(prefix)
            mtl = make_mtl(t, "DARK|GRAY", zcat=self.zcat, trim=False)
            mtl.sort(keys='TARGETID')
            pp = self.post_prio.copy()
            nom = [0, 0, 0, 3, 1]
            # ADM in SV, all quasars get all observations.
            if prefix == "SV1_":
                pp[2], nom[2] = pp[3], nom[3]
            self.assertTrue(np.all(mtl['PRIORITY'] == pp))
            self.assertTrue(np.all(mtl['NUMOBS_MORE'] == nom))
            # - change one target to a SAFE (BADSKY) target and confirm priority=0 not 1
            t[prefix+'DESI_TARGET'][0] = Mx.BAD_SKY
            mtl = make_mtl(t, "DARK|GRAY", zcat=self.zcat, trim=False)
            mtl.sort(keys='TARGETID')
            self.assertEqual(mtl['PRIORITY'][0], 0)

    def test_mtl_io(self):
        """Test MTL correctly handles masked NUMOBS quantities.
        """
        # ADM loop through once for SV and once for the main survey.
        for prefix in ["", "SV1_"]:
            t = self.reset_targets(prefix)
            mtl = make_mtl(t, "BRIGHT", zcat=self.zcat, trim=True)
            testfile = 'test-aszqweladfqwezceas.fits'
            mtl.write(testfile, overwrite=True)
            x = mtl.read(testfile)
            os.remove(testfile)
            if x.masked:
                self.assertTrue(np.all(mtl['NUMOBS_MORE'].mask == x['NUMOBS_MORE'].mask))


if __name__ == '__main__':
    unittest.main()


def test_suite():
    """Allows testing of only this module with the command:

        python setup.py test -m desitarget.test.test_mtl
    """
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
