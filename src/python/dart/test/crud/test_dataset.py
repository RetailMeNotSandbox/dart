import unittest
from dart.client.python.dart_client import Dart
from dart.engine.no_op.metadata import NoOpActionTypes
from dart.model.exception import DartRequestException
from dart.model.dataset import Dataset, DatasetData, Column, DataFormat, DataType, RowFormat, FileFormat, Compression, LoadType


class TestDatasetCrud(unittest.TestCase):
    def setUp(self):
        self.dart = Dart(host='localhost', port=5000)

    def test_crud(self):
        columns = [Column('c1', DataType.VARCHAR, 50), Column('c2', DataType.BIGINT)]
        df = DataFormat(FileFormat.PARQUET, RowFormat.NONE)
        ds = Dataset(
            data=DatasetData(name=NoOpActionTypes.action_that_succeeds.name,
                             table_name=NoOpActionTypes.action_that_succeeds.name,
                             load_type=LoadType.INSERT,
                             location='s3://bucket/prefix',
                             data_format=df,
                             columns=columns,
                             tags=['foo']))
        ds.data.user_id = 'dart@client.rmn'
        posted_dataset = self.dart.save_dataset(ds)
        self.assertEqual(posted_dataset.data.to_dict(), ds.data.to_dict())

        dataset = self.dart.get_dataset(posted_dataset.id)
        self.assertEqual(posted_dataset.to_dict(), dataset.to_dict())

        dataset.data.compression = Compression.GZIP
        put_dataset = self.dart.save_dataset(dataset)
        self.assertEqual(put_dataset.data.compression, Compression.GZIP)
        self.assertNotEqual(posted_dataset.to_dict(), put_dataset.to_dict())

        self.dart.delete_dataset(dataset.id)
        try:
            self.dart.get_dataset(dataset.id)
        except DartRequestException as e:
            self.assertEqual(e.response.status_code, 404)
            return

        self.fail('dataset should have been missing after delete!')


if __name__ == '__main__':
    unittest.main()
