from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from pathlib import Path
import tempfile
from experiments.models import Dataset, ImageFrame
from experiments.services.dataset_import import import_images_from_folder

class SecurityAndImportTests(TestCase):
    @override_settings(REQUIRE_STAFF_AUTH=True)
    def test_anonymous_cannot_read_logs_or_start_gpu_work(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertIn('/admin/login/', self.client.get('/').url)
        user = get_user_model().objects.create_user(username='viewer')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/').status_code, 302)
        user.is_staff = True
        user.save()
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_reimport_after_single_frame_zero_uses_next_index(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'one.jpg').touch()
            dataset = Dataset.objects.create(name='test', data_path=directory)
            import_images_from_folder(dataset)
            (path/'two.jpg').touch()
            import_images_from_folder(dataset)
            self.assertEqual(list(dataset.images.order_by('frame_index').values_list('frame_index', flat=True)), [0,1])
