"""Numerical tolerance regression; does not test Gazebo physics."""
import unittest
import warnings
import numpy as np
from scipy.spatial.transform import Rotation
from check_joint_offsets import frame_errors

class CoordinateToleranceTests(unittest.TestCase):
    def test_near_singular_euler_serialization(self):
        expected=np.eye(4)
        expected[:3,:3]=Rotation.from_euler('xyz',[.7,np.pi/2-5e-8,1.2]).as_matrix()
        with warnings.catch_warnings(record=True):
            angles=Rotation.from_matrix(expected[:3,:3]).as_euler('xyz')
        got=expected.copy();got[:3,:3]=Rotation.from_euler('xyz',angles).as_matrix()
        got[:3,3]=[1.49e-7,0,0]
        frame_errors(got,expected)

    def test_one_millimetre_error_rejected(self):
        got=np.eye(4);got[0,3]=.001
        with self.assertRaises(RuntimeError):frame_errors(got,np.eye(4))

    def test_one_milliradian_error_rejected(self):
        got=np.eye(4);got[:3,:3]=Rotation.from_rotvec([0,0,.001]).as_matrix()
        with self.assertRaises(RuntimeError):frame_errors(got,np.eye(4))

    def test_nan_rejected(self):
        got=np.eye(4);got[0,3]=np.nan
        with self.assertRaises(RuntimeError):frame_errors(got,np.eye(4))

if __name__=='__main__':unittest.main()
