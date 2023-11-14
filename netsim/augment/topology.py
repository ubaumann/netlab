'''
Topology-level transformation:

* Check for required elements (nodes, defaults)
* Check for extraneous elements
* Adjust 'provider' parameter
* Create expanded topology file in YAML format (mostly for troubleshooting purposes)
'''

import os
from box import Box

from ..utils import log
from .. import data
from ..data.validate import validate_attributes,get_object_attributes
from ..data.types import must_be_list,must_be_string,must_be_dict

#
# Extend link/node/global attribute lists with extra attributes
#
def extend_attribute_list(settings: Box, attribute_path: str = 'topology.defaults', always_valid: list = []) -> None:
  if not 'extra_attributes' in settings:
    return

  for k in settings.extra_attributes.keys():           # Iterate over extensions
    if not k in settings.get('attributes',{}):         # Check that the extension is valid
      if k in always_valid:                            # ... some extensions are always valid (needed for modules)
        settings.attributes[k] = []                    # ... in which case we have to start with an empty list
      else:                                            # ... for everything else, throw an error
        log.error(
          f'Invalid extra_attribute {k} -- not present in configurable {attribute_path} attributes',
          log.IncorrectValue,
          'topology')

    must_be_list(                                      # Make sure the extension is a list so it's safe to iterate over
      parent = settings.extra_attributes,
      key = k,
      path = f'{attribute_path}.extra_attributes.{k}')

    log.exit_on_error()

    for v in settings.extra_attributes[k]:             # Have to iterate over values in the custom attribute list
      if not v in settings.attributes[k]:              # ... to prevent duplicate values in attribute lists
        if isinstance(settings.attributes[k],Box):     # Deal with old- or new-style attributes
          settings.attributes[k][v] = None             # ... new style: add element to dictionary
        else:
          settings.attributes[k].append(v)             # ... old style: append it to the list

#
# Extend attribute lists for all top-level elements of the defaults dictionary
# with 'attributes' and 'extra_attributes' keys
#
def extend_module_attribute_list(topology: Box) -> None:
  for k in topology.defaults.keys():
    if isinstance(topology.defaults[k],dict):
      if 'extra_attributes' in topology.defaults[k]:
        if not 'attributes' in topology.defaults[k]:   # pragma: no cover (things would break way before this point)
          topology.defaults[k].attributes = {}
        extend_attribute_list(topology.defaults[k],f'topology.defaults.{k}',['global','node','link'])

def topology_sanity_check(topology: Box) -> None:
  if not 'name' in topology:
    topo_name = os.path.basename(os.path.dirname(os.path.realpath(topology['input'][0])))[:12]
    for bad_char in (' ','.'):
      topo_name = topo_name.replace(bad_char,'_')
    topology.name = topo_name

  if 'module' in topology:
    must_be_list(topology,'module','')
    topology.defaults.module = topology.module

  if must_be_string(topology,'name','',module='topology'):
    topology.defaults.name = topology.name

def check_required_elements(topology: Box) -> None:
  invalid_topo = False
  for rq in ['nodes']:
    if not topology.get(rq):
      log.error(f"Required topology element '{rq}' is missing or empty",category=log.MissingValue,module="topology")
      invalid_topo = True

  if invalid_topo:
    log.fatal("Fatal topology errors, aborting")

def check_global_elements(topology: Box) -> None:
  # Allow provider-specific global attributes
  providers = get_object_attributes(['providers'],topology)

  validate_attributes(
    data=topology,                                  # Validate node data
    topology=topology,
    data_path='topology',                           # Topology path to node name
    data_name=f'topology',
    attr_list=['global','internal'],                # We're checking global (+ internal) attributes
    modules=topology.get('module',[]),              # ... against topology modules
    module='topology',                              # Function is called from 'nodes' module
    extra_attributes = providers)                   # Allow provider-specific settings (not checked at the moment)

#
# Find virtualization provider, set provider and defaults.provider to that value
#
# Note: defaults.provider is needed in some output routines that get defaults data structure
# but not the whole topology
#
def adjust_global_parameters(topology: Box) -> None:
  if not 'provider' in topology:
    topology.provider = topology.defaults.provider
  else:
    topology.defaults.provider = topology.provider

  if not topology.provider:
    log.fatal('Virtualization provider is not defined in either "provider" or "defaults.provider" elements')

  if not must_be_string(topology,'provider','',module='topology'):
    log.exit_on_error()

  providers = topology.defaults.providers
  if not topology.provider in providers:
    plist = ', '.join(sorted(providers.keys()))
    log.fatal(f'Unknown virtualization provider {topology.provider}. Supported providers are: {plist}')

  # Adjust defaults with provider-specific defaults
  #
  for k in ['addressing']:
    if k in topology.defaults.providers[topology.provider]:
      topology.defaults[k] = topology.defaults[k] + topology.defaults.providers[topology.provider][k]

#
# Cleanup the topology
#

def cleanup_topology(topology: Box) -> Box:
  topo_copy = Box(topology,box_dots=True)

  # Remove PFX generators from addressing section
  #
  if not 'addressing' in topo_copy:
    return topo_copy

  for k,v in topo_copy.addressing.items():
    for p in list(v.keys()):
      if "_pfx" in p or "_eui" in p:
        v.pop(p,None)

  return topo_copy
