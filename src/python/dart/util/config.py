

def _get_dart_host(config):
    elb_params = config['cloudformation_stacks']['elb']['boto_args']['Parameters']
    rs_name_param = _get_element(elb_params, 'ParameterKey', 'RecordSetName')
    dart_host = rs_name_param['ParameterValue']
    return dart_host


def _get_element(l, k, v):
    for e in l:
        if e[k] == v:
            return e
    raise Exception('element with %s: %s not found' % (k, v))