import unittest
from unittest.mock import Mock, patch

from media_studio.images import read_image, MAX_PIXELS
from media_studio.jobs import Job


class BoundaryTests(unittest.TestCase):
    def test_invalid_timeouts_do_not_allocate_workers(self):
        with patch('media_studio.jobs.mp.get_context') as context:
            for timeout in (0, -1, float('nan'), float('inf'), True, '120'):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    Job('load', {}, timeout=timeout)
            context.assert_not_called()

    def test_start_failure_closes_queue_without_joining_unstarted_process(self):
        context = Mock()
        process = context.Process.return_value
        process.pid = None
        process.start.side_effect = OSError('cannot start')
        with patch('media_studio.jobs.mp.get_context', return_value=context):
            with self.assertRaises(OSError):
                Job('load', {})
        context.Queue.return_value.close.assert_called_once()
        context.Queue.return_value.cancel_join_thread.assert_called_once()
        process.join.assert_not_called()

    def test_close_is_idempotent_and_closed_job_is_explicit(self):
        with patch('media_studio.jobs.mp.get_context'):
            job = Job('load', {})
            job.close()
            job.close()
            job.messages.close.assert_called_once()
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                job.poll()

    def test_invalid_pixel_budget_is_rejected_before_opening_input(self):
        for limit in (0, -1, True, 1.5, MAX_PIXELS + 1):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'pixel limit'):
                read_image('missing.png', max_pixels=limit)
