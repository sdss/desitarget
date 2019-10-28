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

        # This is a dual identity case. In all cases the target is both QSO and ELG.
        # The first case is a true QSO with lowz.
        # The second case is a true QSO with highz.
        # The third case is an ELG.

        self.type_A = np.array(['QSO', 'QSO', 'ELG'])
        self.type_B = np.array(['ELG', 'ELG', 'QSO'])
        self.priorities_A = np.array([Mx[t].priorities['UNOBS'] for t in self.type_A])
        self.priorities_B = np.array([Mx[t].priorities['UNOBS'] for t in self.type_B])
        self.priorities = np.maximum(self.priorities_A, self.priorities_B)  # get the maximum between the two.
        self.targets['DESI_TARGET'] = np.array([Mx[t].mask for t in self.type_A]) | np.array([Mx[t].mask for t in self.type_B])
        self.targets['BGS_TARGET'] = np.zeros(len(self.type_A), dtype=np.int64)
        self.targets['MWS_TARGET'] = np.zeros(len(self.type_A), dtype=np.int64)

        n = len(self.targets)
        self.targets['ZFLUX'] = 10**((22.5-np.linspace(20, 22, n))/2.5)
        self.targets['TARGETID'] = list(range(n))
        pinit, ninit = initial_priority_numobs(self.targets)
        self.targets["PRIORITY_INIT"] = pinit
        self.targets["NUMOBS_INIT"] = ninit

        # - reverse the order for zcat to make sure joins work.
        self.zcat = Table()
        self.zcat['TARGETID'] = self.targets['TARGETID'][::-1]
        self.zcat['Z'] = [1.0, 1.5, 2.5]
        self.zcat['ZWARN'] = [0, 0, 0]
        self.zcat['NUMOBS'] = [1, 1, 1]
        self.zcat['SPECTYPE'] = ['QSO', 'QSO', 'GALAXY']

        # priorities and numobs more after measuring redshifts.
        self.post_prio = [0 for t in self.type_A]
        self.post_numobs_more = [0 for t in self.type_A]
        self.post_prio[0] = Mx['QSO'].priorities['MORE_ZGOOD']  # highz QSO.
        self.post_prio[1] = Mx['QSO'].priorities['DONE']  # Lowz QSO,  DONE.
        self.post_prio[2] = Mx['ELG'].priorities['DONE']  # ELG, DONE.
        self.post_numobs_more[0] = 3
        self.post_numobs_more[1] = 0
        self.post_numobs_more[2] = 0

    def test_mtl(self):
        """Test output from MTL has the correct column names.
        """
        # ADM loop through once each for the main survey, commissioning and SV.
        # t = self.reset_targets(prefix)
        mtl = make_mtl(self.targets, "GRAY|DARK")
        goodkeys = sorted(set(self.targets.dtype.names) | set(['NUMOBS_MORE', 'PRIORITY', 'OBSCONDITIONS']))
        mtlkeys = sorted(mtl.dtype.names)
        self.assertEqual(mtlkeys, goodkeys)

    def test_numobs(self):
        """Test priorities, numobs and obsconditions are set correctly with no zcat.
        """
        # ADM loop through once for SV and once for the main survey.
        mtl = make_mtl(self.targets, "GRAY|DARK")
        mtl.sort(keys='TARGETID')
        self.assertTrue(np.all(mtl['NUMOBS_MORE'] == [4, 4, 4]))
        self.assertTrue(np.all(mtl['PRIORITY'] == self.priorities))

    def test_zcat(self):
        """Test priorities, numobs and obsconditions are set correctly after zcat.
        """
        # ADM loop through once for SV and once for the main survey.
        mtl = make_mtl(self.targets, "DARK|GRAY", zcat=self.zcat, trim=False)
        mtl.sort(keys='TARGETID')
        self.assertTrue(np.all(mtl['PRIORITY'] == self.post_prio))
        self.assertTrue(np.all(mtl['NUMOBS_MORE'] == self.post_numobs_more))


if __name__ == '__main__':
    unittest.main()


def test_suite():
    """Allows testing of only this module with the command:

        python setup.py test -m desitarget.test.test_mtl
    """
    return unittest.defaultTestLoader.loadTestsFromName(__name__)
