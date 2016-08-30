from dart.util.logging_utils import DartLogger
import os
from pydoc import locate

import pinject

from dart.context.locator import find_injectable_classes
from dart.util.strings import to_snake_case

_logger = DartLogger(__name__)


class AppContext(object):
    def __init__(self, config, exclude_injectable_module_paths):
        self.config = config
        self._instance_bindings = {
            o['name']: locate(o['path'])(**(o.get('options', {}))) for o in config['dart'].get('app_context', [])
        }
        self._instance_bindings.update({'dart_config': config})

        this_dir = os.path.dirname(os.path.abspath(__file__))
        dart_src_root = os.path.abspath(os.path.join(this_dir, '..', '..'))
        self.obj_graph = pinject.new_object_graph(
            modules=None,
            classes=find_injectable_classes([dart_src_root], exclude_injectable_module_paths or []),
            binding_specs=[DartBindingSpec(self._instance_bindings)]
        )
        for obj in config['dart'].get('app_context', []):
            instance = self._instance_bindings[obj['name']]
            if hasattr(instance, 'set_app_context'):
                instance.set_app_context(self)

    def get(self, cls):
        if type(cls) == str and cls in self._instance_bindings:
            return self._instance_bindings[cls]

        snake_case_name = to_snake_case(cls.__name__)
        if snake_case_name in self._instance_bindings:
            return self._instance_bindings[snake_case_name]

        return self.obj_graph.provide(cls)


class DartBindingSpec(pinject.BindingSpec):
    def __init__(self, instance_bindings):
        self.instance_bindings = instance_bindings

    def configure(self, bind):
        for name, instance in self.instance_bindings.iteritems():
            bind(name, to_instance=instance)
