from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from users.serializers import UserSerializer, UserProfileSerializer, UserRegistrationSerializer
from rest_framework.authtoken.models import Token
from django.urls import reverse

User = get_user_model()

class UserModelTest(TestCase):

    def test_create_user(self):
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser(self):
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass'
        )
        self.assertEqual(admin_user.username, 'admin')
        self.assertEqual(admin_user.email, 'admin@example.com')
        self.assertTrue(admin_user.is_active)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

    def test_user_initial_gamification_fields(self):
        user = User.objects.create_user(
            username='gametest',
            email='game@example.com',
            password='gametest123'
        )
        self.assertEqual(user.points, 0)
        self.assertEqual(user.level, 'beginner')
        self.assertEqual(user.contributions_count, 0)
        self.assertEqual(user.verifications_count, 0)
        self.assertFalse(user.is_verified_contributor)

class UserSerializerTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='serializeruser',
            email='serializer@example.com',
            password='testpassword'
        )

    def test_user_serializer(self):
        serializer = UserSerializer(instance=self.user)
        data = serializer.data
        self.assertEqual(data['username'], 'serializeruser')
        self.assertEqual(data['email'], 'serializer@example.com')
        self.assertIn('id', data)

    def test_user_profile_serializer(self):
        serializer = UserProfileSerializer(instance=self.user)
        data = serializer.data
        self.assertEqual(data['username'], 'serializeruser')
        self.assertEqual(data['email'], 'serializer@example.com')
        self.assertEqual(data['points'], 0)
        self.assertEqual(data['level'], 'beginner')
        self.assertEqual(data['contributions_count'], 0)
        self.assertEqual(data['verifications_count'], 0)
        self.assertFalse(data['is_verified_contributor'])
        self.assertIn('badges', data)
        self.assertIn('recent_contributions', data)

class UserRegistrationSerializerTest(APITestCase):

    def test_registration_success(self):
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'strongpass123',
            'password2': 'strongpass123'
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(raise_exception=True))
        user = serializer.save()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'newuser')
        self.assertEqual(user.email, 'newuser@example.com')
        self.assertTrue(user.check_password('strongpass123'))

    def test_registration_password_mismatch(self):
        data = {
            'username': 'mismatchuser',
            'email': 'mismatch@example.com',
            'password': 'pass1',
            'password2': 'pass2'
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('password', serializer.errors)

    def test_registration_duplicate_username(self):
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='somepass'
        )
        data = {
            'username': 'existinguser',
            'email': 'another@example.com',
            'password': 'anotherpass',
            'password2': 'anotherpass'
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('username', serializer.errors)

    def test_registration_duplicate_email(self):
        User.objects.create_user(
            username='userone',
            email='duplicate@example.com',
            password='passone'
        )
        data = {
            'username': 'usertwo',
            'email': 'duplicate@example.com',
            'password': 'passtwo',
            'password2': 'passtwo'
        }
        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('email', serializer.errors)

class UserViewsTest(APITestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='testuser1',
            email='test1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='password123'
        )
        self.client.force_authenticate(user=self.user1)
        self.current_user_url = reverse('users:me-profile')
        self.user_profile_url = reverse('users:user-profile', kwargs={'pk': self.user2.pk})

    def test_current_user_view_authenticated(self):
        response = self.client.get(self.current_user_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], self.user1.username)

    def test_current_user_view_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.current_user_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_profile_view_authenticated(self):
        response = self.client.get(self.user_profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], self.user2.username)

    def test_user_profile_view_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.user_profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class UpdateProfileViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='updateuser',
            email='update@example.com',
            password='password123'
        )
        self.client.force_authenticate(user=self.user)
        self.update_url = reverse('users:update-profile')

    def test_update_profile_authenticated(self):
        data = {'first_name': 'Updated', 'last_name': 'User'}
        response = self.client.patch(self.update_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'User')

    def test_update_profile_unauthenticated(self):
        self.client.force_authenticate(user=None)
        data = {'first_name': 'Unauthorized'}
        response = self.client.patch(self.update_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class UserContributionsViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='contribuser',
            email='contrib@example.com',
            password='password123'
        )
        self.client.force_authenticate(user=self.user)
        self.contributions_url = reverse('users:me-contributions')

        # Create some contributions
        from dictionary.models import KoloquaEntry, WordCategory
        category = WordCategory.objects.create(name='Test Category')
        KoloquaEntry.objects.create(
            koloqua_text='test1', english_translation='test1', contributor=self.user,
            status='verified', categories=category
        )
        KoloquaEntry.objects.create(
            koloqua_text='test2', english_translation='test2', contributor=self.user,
            status='pending', categories=category
        )

    def test_user_contributions_view_authenticated(self):
        response = self.client.get(self.contributions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # Both verified and pending contributions
        self.assertEqual(response.data[0]['koloqua_text'], 'test1')

    def test_user_contributions_view_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.contributions_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class UserListViewTest(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='leaderuser1',
            email='leader1@example.com',
            password='password123',
            points=100,
            contributions_count=5
        )
        self.user2 = User.objects.create_user(
            username='leaderuser2',
            email='leader2@example.com',
            password='password123',
            points=50,
            contributions_count=2
        )
        self.client.force_authenticate(user=self.user1)
        self.leaderboard_url = reverse('users:leaderboard')

    def test_user_list_view_authenticated(self):
        response = self.client.get(self.leaderboard_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # Both users should be in the list
        self.assertEqual(response.data[0]['username'], self.user1.username) # Ordered by points/contributions

    def test_user_list_view_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.leaderboard_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
