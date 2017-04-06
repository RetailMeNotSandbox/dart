#!/usr/bin/env python27

import subprocess
import sys


def call(cmd):
    try:
        print cmd
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
        print result
        return result
    except subprocess.CalledProcessError as e:
        print e.output
        raise e


s3_key = sys.argv[1]
file_name = s3_key.split('/')[-1]
pyspark_script = '/tmp/%s' % file_name

call('aws s3 cp %s %s' % (s3_key, pyspark_script))
call('spark-submit %s' % pyspark_script)
