from dart.util.logging_utils import DartLogger
import os
from pyclbr import readmodule
from pydoc import locate

_logger = DartLogger(__name__)


class ClassRegistry(object):
    def __init__(self):
        self.classes = set()

    def new_class_registering_decorator(self):
        def class_registering_decorator(cls):
            self.classes.add(cls)
            return cls
        return class_registering_decorator

class_registry = ClassRegistry()

injectable = class_registry.new_class_registering_decorator()


def find_injectable_classes(search_paths, exclude_injectable_module_paths=None):
    modules = set()
    for path in search_paths:
        for root, dirs, fnames in os.walk(path):
            for fname in fnames:
                if fname.endswith('.py'):
                    module_path = os.path.relpath(os.path.join(root, fname), path)
                    module = module_path.replace('/', '.')[:-3]
                    fpath = os.path.join(root, fname)
                    has_import = False
                    has_decorator = False
                    with open(fpath) as f:
                        for line in f:
                            if 'dart.context.locator' in line:
                                has_import = True
                            if '@injectable' in line:
                                has_decorator = True
                            if has_import and has_decorator:
                                break
                    if has_import and has_decorator and not path_excluded(module, exclude_injectable_module_paths):
                        modules.add(module)

    for module in modules:
        class_metadata = readmodule(module)
        for class_name in class_metadata.keys():
            # the line below will load the class, which causes the @injectable code to run,
            # registering the class (assuming the module search was not a false positive)
            locate(module + '.' + class_name)

    classes_by_name = {cls.__name__: cls for cls in class_registry.classes}
    for class_name in sorted(classes_by_name.keys()):
        _logger.info('injectable class registered: %s' % class_name)

    return classes_by_name.values()


def path_excluded(path, exclude_class_paths):
    if not exclude_class_paths:
        return False
    for excluded_path in exclude_class_paths:
        if path.startswith(excluded_path):
            return True
    return False
