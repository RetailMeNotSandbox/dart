import boto3
import bz2
import csv
import dateutil.parser
import magic
import math
import os
import re
import zlib

from datetime import datetime
from dart.model.dataset import DataType, Column, Dataset, DatasetData, DataFormat, FileFormat, RowFormat, LoadType
from s3 import get_bucket_name, get_key_name


def infer_dataset_data(s3_path, max_lines):
    """
    :type s3_path: str
    :param s3_path: The full s3 path to a sample delimited dataset
        file.

    :type max_lines: int
    :param max_lines: The maximum number of lines to peek.
    """
    guesses, has_header, compression, dialect = get_guesses(s3_path, max_lines)
    columns = columns_with_best_guess(guesses, has_header)
    location = guess_location(s3_path)
    return Dataset(data=DatasetData(name='guessed_dataset',
                                    table_name='public',
                                    data_format=DataFormat(
                                        file_format=FileFormat.TEXTFILE,
                                        row_format=RowFormat.DELIMITED,
                                        delimited_by=dialect.delimiter,
                                        escaped_by=dialect.escapechar,
                                        quoted_by=dialect.quotechar,
                                    ),
                                    location=location,
                                    columns=columns,
                                    compression=compression,
                                    load_type=LoadType.INSERT))


def guess_location(s3_path):
    """
    :type s3_path: str
    :param s3_path: The full s3 path to a sample delimited dataset
        file.
    """
    return os.path.dirname(s3_path)


def get_guesses(s3_path, max_lines=1000):
    """
    :type s3_path: str
    :param s3_path: The full s3 path to a sample delimited dataset
        file.

    :type max_lines: int
    :param max_lines: The maximum number of lines to peek.
    """
    chunk_size = 1024
    bucket = get_bucket_name(s3_path)
    client = boto3.client('s3')
    # Dart assumes s3_path could be a prefix. If so, Dart will get the first key object in the given prefix
    key = client.list_objects(Bucket=bucket, MaxKeys=1, Prefix=get_key_name(s3_path))['Contents'][0]['Key']
    stream = client.get_object(Bucket=bucket, Key=key)['Body']
    # Read the first chunk of the file stream
    preview = stream.read(chunk_size)
    compression = re.search(r'ascii|gzip|bzip', magic.from_buffer(preview).lower()).group(0)

    guess_functions = {
        'ascii': get_ascii_guesses,
        'gzip': get_gzip_guesses,
        'bzip': get_bzip_guesses
    }
    return guess_functions[compression](preview, stream, chunk_size, max_lines)


def get_ascii_guesses(preview, stream, chunk_size, max_lines):
    """
    :type preview: str
    :param preview: The initial chunk of content read from the s3
        file stream.

    :type stream: botocore.response.StreamingBody
    :param stream: StreamingBody object of the s3 dataset file.

    :type chunk_size: int
    :param chunk_size: Maximum size of the chunk in bytes peeking.

    :type max_lines: int
    :param max_lines: Maximum number of lines to peek into.
    """
    COMPRESSION_TYPE = 'NONE'
    guesses = dict()
    dialect = csv.Sniffer().sniff(preview)
    has_header = csv.Sniffer().has_header(preview)
    lines_read = 0
    first_row = True
    data = ''

    while True:
        if first_row:
            chunk = preview
        else:
            chunk = stream.read(chunk_size)
        if not chunk:
            break
        data += chunk
        if '\n' in data:
            guesses, data, lines_read = analyze_data(data, lines_read, max_lines, first_row, guesses, dialect, has_header)
            first_row = False
            if lines_read >= max_lines:
                return guesses, has_header, COMPRESSION_TYPE, dialect
    return guesses, has_header, COMPRESSION_TYPE, dialect


def get_gzip_guesses(preview, stream, chunk_size, max_lines):
    """
    :type preview: str
    :param preview: The initial chunk of content read from the s3
        file stream.

    :type stream: botocore.response.StreamingBody
    :param stream: StreamingBody object of the s3 dataset file.

    :type chunk_size: int
    :param chunk_size: Maximum size of the chunk in bytes peeking.

    :type max_lines: int
    :param max_lines: Maximum number of lines to peek into.
    """
    COMPRESSION_TYPE = 'GZIP'
    guesses = dict()
    dialect = csv.Sniffer().sniff(zlib.decompressobj(zlib.MAX_WBITS|16).decompress(preview))
    has_header = csv.Sniffer().has_header(zlib.decompressobj(zlib.MAX_WBITS|16).decompress(preview))
    d = zlib.decompressobj(zlib.MAX_WBITS|16)
    lines_read = 0
    first_row = True
    data = ''

    while True:
        if first_row:
            chunk = preview
        else:
            chunk = stream.read(chunk_size)
        if not chunk:
            break
        data += d.decompress(chunk)
        if '\n' in data:
            guesses, data, lines_read = analyze_data(data, lines_read, max_lines, first_row, guesses, dialect, has_header)
            first_row = False
            if lines_read >= max_lines:
                return guesses, has_header, COMPRESSION_TYPE, dialect
    return guesses, has_header, COMPRESSION_TYPE, dialect


def get_bzip_guesses(preview, stream, chunk_size, max_lines):
    """
    :type preview: str
    :param preview: The initial chunk of content read from the s3
        file stream.

    :type stream: botocore.response.StreamingBody
    :param stream: StreamingBody object of the s3 dataset file.

    :type chunk_size: int
    :param chunk_size: Maximum size of the chunk in bytes peeking.

    :type max_lines: int
    :param max_lines: Maximum number of lines to peek into.
    """
    COMPRESSION_TYPE = 'BZ2'
    guesses = dict()
    dialect = csv.Sniffer().sniff(bz2.BZ2Decompressor().decompress(preview))
    has_header = csv.Sniffer().has_header(bz2.BZ2Decompressor().decompress(preview))
    lines_read = 0
    first_row = True
    data = ''

    while True:
        if first_row:
            chunk = preview
        else:
            chunk = stream.read(chunk_size)
        if not chunk:
            break
        data += bz2.BZ2Decompressor().decompress(chunk)
        if '\n' in data:
            guesses, data, lines_read = analyze_data(data, lines_read, max_lines, first_row, guesses, dialect, has_header)
            first_row = False
            if lines_read >= max_lines:
                return guesses, has_header, COMPRESSION_TYPE, dialect
    return guesses, has_header, COMPRESSION_TYPE, dialect


def analyze_data(data, lines_read, max_lines, first_row, guesses, dialect, has_header):
    """
    :type data: str
    :param data: The data to analyze.

    :type lines_read: int
    :param lines_read: Total number of lines read so far.

    :type max_lines: int
    :param max_lines: The maximum number of lines to peek.

    :type first_row: bool
    :param first_row: True if first row.

    :type guesses: dict
    :param guesses: The dictionary object containing all guesses.

    :type dialect: csv.Dialect
    :param dialect: Dialect object derived from the preview of
        the data file.

    :type has_header: bool
    :param has_header: True if file has headers.
    """
    rows = data.split('\n')
    if first_row:
        guesses = analyze_header(rows[0], guesses, dialect, has_header)
    for row in rows[1:-1]:
        if lines_read < max_lines:
            guesses = analyze_row(row, guesses, dialect)
            lines_read += 1
        else:
            return guesses, data, lines_read
    data = ''
    return guesses, data, lines_read


def analyze_header(row, guesses, dialect, has_header):
    """
    :type row: str
    :param s3_path: The row to analyze.

    :type guesses: dict
    :param guesses: The dictionary object containing all guesses.

    :type dialect: csv.Dialect
    :param dialect: Dialect object derived from the preview of
        the data file.

    :type has_header: bool
    :param has_header: True if the file has headers.
    """
    if has_header:
        headers = row.split(dialect.delimiter)
        for idx, header in enumerate(headers):
            header = header.strip('"')
            guesses[idx] = {'name': header, 'guesses': set()}
    else:
        headers = row.split(dialect.delimiter)
        for idx, header in enumerate(headers):
            guesses[idx] = {'guesses': set()}
    return guesses


def analyze_row(row, guesses, dialect):
    """
    :type row: str
    :param s3_path: The row to analyze.

    :type guesses: dict
    :param guesses: The dictionary object containing all guesses.

    :type dialect: csv.Dialect
    :param dialect: Dialect object derived from the preview of
        the data file.
    """
    cur_row = row.split(dialect.delimiter)
    for idx, value in enumerate(cur_row):
        value = value.strip('"')
        guess = guess_data_type(value)
        guesses[idx]['guesses'].add(guess)

        if guess == DataType.VARCHAR:
            current_max = guesses[idx].get('varcharlength', 1)
            guesses[idx]['varcharlength'] = max(current_max, len(value))
        if guess == 'null':
            guesses[idx]['varcharlength'] = 1
    return guesses


def guess_data_type(value):
    """
    :param value: The value to infer.
    """
    if value.lower() == 'null':
        return 'null'
    try:
        retval = float(value)
        if retval.is_integer():
            if 0 <= retval <= 1:
                return DataType.BOOLEAN
            elif -32768 <= retval <= 32767:
                return DataType.SMALLINT
            elif -2147483648 <= retval <= 2147483647:
                return DataType.INT
            elif -9223372036854775808 <= retval <= 9223372036854775807:
                return DataType.BIGINT
        else:
            if -3.4 * math.pow(10,38) <= value <= -1.18 * math.pow(10,-38) or 1.18 * math.pow(10,-38) <= value <= 3.4 * math.pow(10,38):
                return DataType.FLOAT
            else:
                return DataType.NUMERIC
    except:
        try:
            retval = str(value)
            if retval.lower() == 'true' or retval.lower() == 'false':
                return DataType.BOOLEAN
            else:
                try:
                    time = dateutil.parser(value)
                    if datetime(1970,1,1,0,0,1) <= time <= datetime(2038,1,19,3,14,7):
                        return DataType.TIMESTAMP
                    else:
                        return DataType.DATETIME
                except:
                    try:
                        datetime.strptime(value, '%Y-%m-%d')
                        return DataType.DATE
                    except:
                        return DataType.VARCHAR
        except:
            return 'null'


def best_guess_from_set(guess_set):
    """
    :type guess_set: set
    :param guess_set: The set contatining all possible guesses
        for a certain column.
    """
    hierarchy = {
        DataType.VARCHAR: 10,
        DataType.TIMESTAMP: 9,
        DataType.DATETIME: 8,
        DataType.DATE: 7,
        DataType.NUMERIC: 6,
        DataType.FLOAT: 5,
        DataType.BIGINT: 4,
        DataType.INT: 3,
        DataType.SMALLINT: 2,
        DataType.BOOLEAN: 1,
        'null': 0
    }
    max_val = -1
    best = None
    for data_type_guess in guess_set:
        if hierarchy[data_type_guess] > max_val:
            max_val = hierarchy[data_type_guess]
            best = data_type_guess
    return best


def columns_with_best_guess(guesses, has_header):
    """
    :type guesses: dict
    :param guesses: Dictionary that represents all guesses for
        each column in the dataset.

    :type has_header: bool
    :param has_header: True if file has header.
    """
    columns = []
    for idx in guesses:
        guess_set = guesses[idx]['guesses']
        data_type = best_guess_from_set(guess_set)
        length = 1

        if data_type == DataType.VARCHAR or data_type == 'null':
            max_len = guesses[idx]['varcharlength']
            # Round up length to nearest power of 2
            length = 2 ** (int(math.log(max_len, 2)) + 1)
            data_type = DataType.VARCHAR

        columns.append(Column
                       (name=guesses[idx]['name'] if has_header else 'col_{}'.format(idx+1),
                        data_type=data_type,
                        length=length if length else 0))
    return columns
