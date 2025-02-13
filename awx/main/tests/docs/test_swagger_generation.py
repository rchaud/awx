import datetime
import json
import re

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.functional import Promise
from django.utils.encoding import force_str

from drf_yasg.codecs import OpenAPICodecJson
import pytest

from awx.api.versioning import drf_reverse


class i18nEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Promise):
            return force_str(obj)
        if type(obj) == bytes:
            return force_str(obj)
        return super(i18nEncoder, self).default(obj)


@pytest.mark.django_db
class TestSwaggerGeneration:
    """
    This class is used to generate a Swagger/OpenAPI document for the awx
    API.  A _prepare fixture generates a JSON blob containing OpenAPI data,
    individual tests have the ability modify the payload.

    Finally, the JSON content is written to a file, `swagger.json`, in the
    current working directory.

    $ py.test test_swagger_generation.py --version 3.3.0

    To customize the `info.description` in the generated OpenAPI document,
    modify the text in `awx.api.templates.swagger.description.md`
    """

    JSON = {}

    @pytest.fixture(autouse=True, scope='function')
    def _prepare(self, get, admin):
        if not self.__class__.JSON:
            url = drf_reverse('api:schema-swagger-ui') + '?format=openapi'
            response = get(url, user=admin)
            codec = OpenAPICodecJson([])
            data = codec.generate_swagger_object(response.data)
            if response.has_header('X-Deprecated-Paths'):
                data['deprecated_paths'] = json.loads(response['X-Deprecated-Paths'])

            data['host'] = None
            data['schemes'] = ['https']
            data['consumes'] = ['application/json']

            revised_paths = {}
            deprecated_paths = data.pop('deprecated_paths', [])
            for path, node in data['paths'].items():
                # change {version} in paths to the actual default API version (e.g., v2)
                revised_paths[path.replace('{version}', settings.REST_FRAMEWORK['DEFAULT_VERSION'])] = node
                for method in node:
                    # Ignore any parameters methods, these cause issues because it can come as an array instead of a dict
                    # Which causes issues in the last for loop in here
                    if method == 'parameters':
                        continue

                    if path in deprecated_paths:
                        node[method]['deprecated'] = True
                    if 'description' in node[method]:
                        # Pop off the first line and use that as the summary
                        lines = node[method]['description'].splitlines()
                        # If there was a description then set the summary as the description, otherwise make something up
                        if lines:
                            node[method]['summary'] = lines.pop(0).strip('#:')
                        else:
                            node[method]['summary'] = f'No Description for {method} on {path}'
                        node[method]['description'] = '\n'.join(lines)

                    # remove the required `version` parameter
                    for param in node[method].get('parameters'):
                        if param['in'] == 'path' and param['name'] == 'version':
                            node[method]['parameters'].remove(param)
            data['paths'] = revised_paths
            self.__class__.JSON = data

    def test_sanity(self, release, request):
        JSON = self.__class__.JSON
        JSON['info']['version'] = release

        if not request.config.getoption('--genschema'):
            JSON['modified'] = datetime.datetime.utcnow().isoformat()

        # Make some basic assertions about the rendered JSON so we can
        # be sure it doesn't break across DRF upgrades and view/serializer
        # changes.
        assert len(JSON['paths'])

        # The number of API endpoints changes over time, but let's just check
        # for a reasonable number here; if this test starts failing, raise/lower the bounds
        paths = JSON['paths']
        assert 250 < len(paths) < 400
        assert set(list(paths['/api/'].keys())) == set(['get', 'parameters'])
        assert set(list(paths['/api/v2/'].keys())) == set(['get', 'parameters'])
        assert set(list(sorted(paths['/api/v2/credentials/'].keys()))) == set(['get', 'post', 'parameters'])
        assert set(list(sorted(paths['/api/v2/credentials/{id}/'].keys()))) == set(['delete', 'get', 'patch', 'put', 'parameters'])
        assert set(list(paths['/api/v2/settings/'].keys())) == set(['get', 'parameters'])
        assert set(list(paths['/api/v2/settings/{category_slug}/'].keys())) == set(['get', 'put', 'patch', 'delete', 'parameters'])

    @pytest.mark.parametrize(
        'path',
        [
            '/api/',
            '/api/v2/',
            '/api/v2/ping/',
            '/api/v2/config/',
        ],
    )
    def test_basic_paths(self, path, get, admin):
        # hit a couple important endpoints so we always have example data
        get(path, user=admin, expect=200)

    def test_autogen_response_examples(self, swagger_autogen, request):
        for pattern, node in TestSwaggerGeneration.JSON['paths'].items():
            pattern = pattern.replace('{id}', '[0-9]+')
            pattern = pattern.replace(r'{category_slug}', r'[a-zA-Z0-9\-]+')
            for path, result in swagger_autogen.items():
                if re.match(r'^{}$'.format(pattern), path):
                    for key, value in result.items():
                        method, status_code = key
                        content_type, resp, request_data = value
                        if method in node:
                            status_code = str(status_code)
                            if content_type:
                                produces = node[method].setdefault('produces', [])
                                if content_type not in produces:
                                    produces.append(content_type)
                            if request_data and status_code.startswith('2'):
                                # DRF builds a schema based on the serializer
                                # fields.  This is _pretty good_, but if we
                                # have _actual_ JSON examples, those are even
                                # better and we should use them instead
                                for param in node[method].get('parameters'):
                                    if param['in'] == 'body':
                                        node[method]['parameters'].remove(param)
                                if request.config.getoption("--genschema"):
                                    pytest.skip("In schema generator skipping swagger generator", allow_module_level=True)
                                else:
                                    node[method].setdefault('parameters', []).append(
                                        {
                                            'name': 'data',
                                            'in': 'body',
                                            'schema': {'example': request_data},
                                        }
                                    )

                            # Build response examples
                            if resp:
                                if content_type.startswith('text/html'):
                                    continue
                                if content_type == 'application/json':
                                    resp = json.loads(resp)
                                node[method]['responses'].setdefault(status_code, {}).setdefault('examples', {})[content_type] = resp

    @classmethod
    def teardown_class(cls):
        with open('swagger.json', 'w') as f:
            data = json.dumps(cls.JSON, cls=i18nEncoder, indent=2, sort_keys=True)
            # replace ISO dates w/ the same value so we don't generate
            # needless diffs
            data = re.sub(r'[0-9]{4}-[0-9]{2}-[0-9]{2}(T|\s)[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]+(Z|\+[0-9]{2}:[0-9]{2})?', r'2018-02-01T08:00:00.000000Z', data)
            data = re.sub(r'''(\s+"client_id": ")([a-zA-Z0-9]{40})("\,\s*)''', r'\1xxxx\3', data)
            data = re.sub(r'"action_node": "[^"]+"', '"action_node": "awx"', data)

            # replace uuids to prevent needless diffs
            pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            data = re.sub(pattern, r'00000000-0000-0000-0000-000000000000', data)
            f.write(data)
