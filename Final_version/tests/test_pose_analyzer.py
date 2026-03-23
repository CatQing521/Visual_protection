# tests/test_pose_analyzer.py
import unittest
from core.pose_analyzer import PoseAnalyzer

class TestPoseAnalyzer(unittest.TestCase):
    def test_initialization(self):
        analyzer = PoseAnalyzer()
        self.assertIsNotNone(analyzer)