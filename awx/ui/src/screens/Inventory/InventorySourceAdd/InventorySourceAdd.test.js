import React from 'react';
import { act } from 'react-dom/test-utils';
import { createMemoryHistory } from 'history';
import { InventorySourcesAPI, ProjectsAPI } from 'api';
import {
  mountWithContexts,
  waitForElement,
} from '../../../../testUtils/enzymeHelpers';
import InventorySourceAdd from './InventorySourceAdd';

jest.mock('../../../api');
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useParams: () => ({
    id: 111,
  }),
}));

describe('<InventorySourceAdd />', () => {
  let wrapper;
  const invSourceData = {
    credential: { id: 222 },
    description: 'bar',
    inventory: 111,
    name: 'foo',
    overwrite: false,
    overwrite_vars: false,
    source: 'scm',
    source_path: 'mock/file.sh',
    source_project: { id: 999 },
    source_vars: '---↵',
    update_cache_timeout: 0,
    update_on_launch: false,
    verbosity: 1,
  };

  const mockInventory = {
    id: 111,
    name: 'Foo',
    organization: 2,
  };

  beforeEach(async () => {
    InventorySourcesAPI.readOptions.mockResolvedValue({
      data: {
        actions: {
          GET: {
            source: {
              choices: [
                ['file', 'File, Directory or Script'],
                ['scm', 'Sourced from a Project'],
                ['ec2', 'Amazon EC2'],
                ['gce', 'Google Compute Engine'],
                ['azure_rm', 'Microsoft Azure Resource Manager'],
                ['vmware', 'VMware vCenter'],
                ['satellite6', 'Red Hat Satellite 6'],
                ['openstack', 'OpenStack'],
                ['rhv', 'Red Hat Virtualization'],
                [
                  'openshift_virtualization',
                  'Red Hat OpenShift Virtualization',
                ],
                ['controller', 'Red Hat Ansible Automation Platform'],
              ],
            },
          },
        },
      },
    });

    ProjectsAPI.readInventories.mockResolvedValue({
      data: [],
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('new form displays primary form fields', async () => {
    await act(async () => {
      wrapper = mountWithContexts(
        <InventorySourceAdd inventory={mockInventory} />
      );
    });
    await waitForElement(wrapper, 'ContentLoading', (el) => el.length === 0);
    expect(wrapper.find('FormGroup[label="Name"]')).toHaveLength(1);
    expect(wrapper.find('FormGroup[label="Description"]')).toHaveLength(1);
    expect(wrapper.find('FormGroup[label="Source"]')).toHaveLength(1);
    expect(wrapper.find('FormGroup[label="Ansible Environment"]')).toHaveLength(
      0
    );
  });

  test('should navigate to inventory sources list when cancel is clicked', async () => {
    const history = createMemoryHistory({});
    await act(async () => {
      wrapper = mountWithContexts(
        <InventorySourceAdd inventory={mockInventory} />,
        {
          context: { router: { history } },
        }
      );
    });
    await act(async () => {
      wrapper.find('InventorySourceForm').invoke('onCancel')();
    });
    expect(history.location.pathname).toEqual(
      '/inventories/inventory/111/sources'
    );
  });

  test('should post to the api when submit is clicked', async () => {
    InventorySourcesAPI.create.mockResolvedValueOnce({ data: {} });
    await act(async () => {
      wrapper = mountWithContexts(
        <InventorySourceAdd inventory={mockInventory} />
      );
    });
    await act(async () => {
      wrapper.find('InventorySourceForm').invoke('onSubmit')(invSourceData);
    });
    expect(InventorySourcesAPI.create).toHaveBeenCalledTimes(1);
    expect(InventorySourcesAPI.create).toHaveBeenCalledWith({
      ...invSourceData,
      credential: 222,
      source_project: 999,
      source_script: null,
      execution_environment: null,
    });
  });

  test('successful form submission should trigger redirect', async () => {
    const history = createMemoryHistory({});
    InventorySourcesAPI.create.mockResolvedValueOnce({
      data: { id: 123, inventory: 111 },
    });
    await act(async () => {
      wrapper = mountWithContexts(
        <InventorySourceAdd inventory={mockInventory} />,
        {
          context: { router: { history } },
        }
      );
    });
    await act(async () => {
      wrapper.find('InventorySourceForm').invoke('onSubmit')(invSourceData);
    });
    expect(history.location.pathname).toEqual(
      '/inventories/inventory/111/sources/123/details'
    );
  });

  test('unsuccessful form submission should show an error message', async () => {
    const error = {
      response: {
        data: { detail: 'An error occurred' },
      },
    };
    InventorySourcesAPI.create.mockImplementation(() => Promise.reject(error));
    await act(async () => {
      wrapper = mountWithContexts(
        <InventorySourceAdd inventory={mockInventory} />
      );
    });
    expect(wrapper.find('FormSubmitError').length).toBe(0);
    await act(async () => {
      wrapper.find('InventorySourceForm').invoke('onSubmit')({});
    });
    wrapper.update();
    expect(wrapper.find('FormSubmitError').length).toBe(1);
  });
});
