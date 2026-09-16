import json
import os
import secrets
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest import TestCase, skipUnless


class ConfigurationTests(TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.environment = os.environ.copy()
        for name in list(self.environment):
            if name.upper() in (
                'DJANGO_ENV', 'DJANGO_SETTINGS_MODULE', 'RESOURCECONNECTOR_DEMO_KEY',
            ):
                self.environment.pop(name)
        self.environment.update({
            'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
            'AZURE_POSTGRESQL_NAME': 'configuration_tests',
            'AZURE_POSTGRESQL_HOST': 'localhost',
            'AZURE_POSTGRESQL_USER': 'configuration_tests',
            'AZURE_POSTGRESQL_PASSWORD': secrets.token_urlsafe(32),
            'WEBSITE_SITE_NAME': 'configuration-tests',
            'DBPASS': secrets.token_urlsafe(32) + ' %!^&"<>|',
            'ResourceConnector_demo_Key': secrets.token_urlsafe(32),
        })

    def run_process(self, command, **overrides):
        environment = self.environment.copy()
        for name, value in overrides.items():
            if value is None:
                environment.pop(name, None)
            else:
                environment[name] = value
        return subprocess.run(
            command, cwd=str(self.root), env=environment,
            capture_output=True, text=True,
        )

    def run_python(self, code, **overrides):
        return self.run_process(
            [sys.executable, '-c', textwrap.dedent(code)], **overrides,
        )

    def assert_python_succeeds(self, code, **overrides):
        result = self.run_python(code, **overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_missing_or_blank_secret_prevents_startup(self):
        for module in ('azuresite.settings', 'azuresite.production'):
            for value in (None, '', ' \t\r\n'):
                with self.subTest(module=module, value=value):
                    result = self.run_python(
                        'import ' + module, DJANGO_SECRET_KEY=value,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('ImproperlyConfigured', result.stderr)
                    self.assertIn('DJANGO_SECRET_KEY must be configured', result.stderr)

    def test_supplied_key_is_used_in_common_and_production_settings(self):
        self.assert_python_succeeds("""
            import os
            from azuresite import settings, production
            assert settings.SECRET_KEY == os.environ['DJANGO_SECRET_KEY']
            assert production.SECRET_KEY == os.environ['DJANGO_SECRET_KEY']
        """)

    def test_debugging_requires_explicit_development_mode(self):
        for mode in (None, 'production', 'development', 'unexpected'):
            with self.subTest(mode=mode):
                self.assert_python_succeeds("""
                    import os
                    from azuresite import settings
                    assert settings.DEBUG is (os.environ.get('DJANGO_ENV') == 'development')
                    assert settings.ALLOWED_HOSTS == ['localhost', '127.0.0.1', '[::1]']
                """, DJANGO_ENV=mode)

    def test_production_overrides_development_debugging(self):
        self.assert_python_succeeds("""
            import os
            from azuresite import production
            assert production.DEBUG is False
            assert production.ALLOWED_HOSTS == [
                'configuration-tests.azurewebsites.net', '127.0.0.1',
            ]
            assert production.DATABASES['default']['PASSWORD'] == os.environ[
                'AZURE_POSTGRESQL_PASSWORD'
            ]
        """, DJANGO_ENV='development')

    def test_wsgi_and_management_commands_select_production(self):
        check = (
            "from django.conf import settings; "
            "assert settings.SETTINGS_MODULE == 'azuresite.production'; "
            "assert settings.DEBUG is False"
        )
        self.assert_python_succeeds(
            'import azuresite.wsgi; ' + check, DJANGO_ENV='production',
        )
        result = self.run_process(
            [sys.executable, 'manage.py', 'shell', '-c', check],
            DJANGO_ENV='production',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_error_responses_hide_debug_details(self):
        for debug_control in ('0', '1'):
            for status in (404, 500):
                with self.subTest(debug_control=debug_control, status=status):
                    result = self.assert_python_succeeds("""
                        import json
                        import logging
                        import os
                        import types
                        import django
                        from django.conf import settings
                        from django.core.handlers.wsgi import WSGIHandler
                        from django.test import RequestFactory, override_settings
                        from django.urls import path

                        django.setup()
                        logging.disable(logging.CRITICAL)
                        if os.environ['DEBUG_CONTROL'] == '1':
                            settings.DEBUG = True

                        def error_view(request):
                            private_value = os.environ['RESPONSE_TEST_SECRET']
                            raise RuntimeError('intentional-response-test-error')

                        urlconf = types.ModuleType('security_test_urls')
                        urlconf.urlpatterns = [path('security-error/', error_view)]
                        target = (
                            '/security-error/' if os.environ['STATUS'] == '500'
                            else '/unknown-route/'
                        )
                        with override_settings(ROOT_URLCONF=urlconf):
                            request = RequestFactory().get(
                                target,
                                HTTP_HOST='configuration-tests.azurewebsites.net',
                            )
                            response = WSGIHandler().get_response(request)
                            body = response.content.decode('utf-8')
                        print(json.dumps({
                            'status': response.status_code,
                            'debug': settings.DEBUG,
                            'secret_visible': os.environ['RESPONSE_TEST_SECRET'] in body,
                            'route_visible': 'security-error/' in body,
                        }))
                    """, DJANGO_SETTINGS_MODULE='azuresite.production',
                        DEBUG_CONTROL=debug_control, STATUS=str(status),
                        RESPONSE_TEST_SECRET=secrets.token_urlsafe(32))
                    response = json.loads(result.stdout)
                    self.assertEqual(response['status'], status)
                    self.assertEqual(response['debug'], debug_control == '1')
                    field = 'secret_visible' if status == 500 else 'route_visible'
                    self.assertEqual(response[field], debug_control == '1')

    @skipUnless(os.name == 'nt', 'Windows batch script')
    def test_batch_script_requires_external_credentials(self):
        for name in ('DBPASS', 'ResourceConnector_demo_Key'):
            for value in (None, ''):
                with self.subTest(name=name, value=value):
                    result = self.run_process(
                        [os.environ['COMSPEC'], '/d', '/c', 'call .\\env.bat'],
                        **{name: value},
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name, result.stderr)

    @skipUnless(os.name == 'nt', 'Windows batch script')
    def test_batch_script_preserves_supplied_credentials(self):
        check = (
            "import os; "
            "assert os.environ['DBPASS'] == os.environ['EXPECTED_DBPASS']; "
            "assert os.environ['ResourceConnector_demo_Key'] == os.environ['EXPECTED_KEY']; "
            "assert os.environ['DJANGO_ENV'] == 'production'"
        )
        result = self.run_process(
            '"{}" /d /s /c "call .\\env.bat && "{}" -c "{}""'.format(
                os.environ['COMSPEC'], sys.executable, check,
            ),
            EXPECTED_DBPASS=self.environment['DBPASS'],
            EXPECTED_KEY=self.environment['ResourceConnector_demo_Key'],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @skipUnless(shutil.which('pwsh') or shutil.which('powershell'), 'PowerShell required')
    def test_powershell_script_requires_and_preserves_external_password(self):
        shell = shutil.which('pwsh') or shutil.which('powershell')
        command = [
            shell, '-NoProfile', '-NonInteractive', '-Command',
            "$ErrorActionPreference = 'Stop'; . .\\env.ps1; "
            "if ($env:DBPASS -cne $env:EXPECTED_DBPASS) { throw 'Password changed.' }",
        ]
        for value in (None, '', self.environment['DBPASS']):
            with self.subTest(password_present=bool(value)):
                result = self.run_process(command, DBPASS=value, EXPECTED_DBPASS=value)
                if value:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('DBPASS', result.stderr)

    @skipUnless(shutil.which('bash'), 'Bash required')
    def test_shell_script_requires_and_preserves_external_password(self):
        shell = shutil.which('bash')
        for command in ([shell, 'env.sh'], [shell, '-c', 'source env.sh']):
            for value in (None, ''):
                with self.subTest(command=command[1:], password_present=bool(value)):
                    result = self.run_process(command, DBPASS=value)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('DBPASS', result.stderr)
        result = self.run_process(
            [shell, '-c', 'source env.sh && [ "$DBPASS" = "$EXPECTED_DBPASS" ]'],
            EXPECTED_DBPASS=self.environment['DBPASS'],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
