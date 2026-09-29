from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from chats.models import Conversation, Message, MessageAttachment

User = get_user_model()


class ChatViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='password123',
            first_name='Alice'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='password123',
            first_name='Bob'
        )

        self.conv = Conversation.objects.create()
        self.conv.participants.add(self.user1, self.user2)

        self.msg1 = Message.objects.create(
            conversation=self.conv,
            sender=self.user1,
            body='Hello Bob'
        )
        self.msg2 = Message.objects.create(
            conversation=self.conv,
            sender=self.user2,
            body='Hi Alice'
        )

    def test_conversation_list_requires_login(self):
        url = reverse('chats:conversation_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_conversation_list_authenticated(self):
        self.client.force_login(self.user1)
        url = reverse('chats:conversation_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bob')
        self.assertContains(response, 'Hi Alice')

    def test_conversation_detail_view(self):
        self.client.force_login(self.user1)
        url = reverse('chats:conversation_detail', kwargs={'pk': self.conv.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bob')
        self.assertContains(response, 'Hello Bob')
        self.assertContains(response, 'Hi Alice')

    def test_start_conversation_with_self_forbidden(self):
        self.client.force_login(self.user1)
        url = reverse('chats:start_conversation')
        response = self.client.post(url, {'seller_user_id': self.user1.pk})
        self.assertEqual(response.status_code, 400)

    def test_start_conversation_success(self):
        self.client.force_login(self.user1)
        url = reverse('chats:start_conversation')
        response = self.client.post(url, {
            'seller_user_id': self.user2.pk,
            'initial_message': 'Checking your listing'
        })
        self.assertEqual(response.status_code, 302)
        # Should reuse the existing conversation between user1 and user2
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertTrue(Message.objects.filter(body='Checking your listing').exists())

    def test_message_history_ajax(self):
        self.client.force_login(self.user1)
        url = reverse('chats:message_history', kwargs={'pk': self.conv.pk})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('messages', data)
        self.assertEqual(len(data['messages']), 2)

    def test_upload_attachment_invalid_mime(self):
        self.client.force_login(self.user1)
        url = reverse('chats:upload_attachment')
        file = SimpleUploadedFile("test.txt", b"plain text", content_type="text/plain")
        response = self.client.post(url, {'file': file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_upload_attachment_success(self):
        self.client.force_login(self.user1)
        url = reverse('chats:upload_attachment')
        # Tiny 1x1 GIF
        gif_bytes = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        file = SimpleUploadedFile("test.gif", gif_bytes, content_type="image/gif")
        response = self.client.post(url, {'file': file})
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment_id', response.json())
        self.assertTrue(MessageAttachment.objects.filter(uploaded_by=self.user1).exists())
