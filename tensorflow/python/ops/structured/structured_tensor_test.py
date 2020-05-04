# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for StructuredTensor."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import parameterized
import numpy as np

from tensorflow.python.eager import context
from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import errors
from tensorflow.python.framework import ops
from tensorflow.python.framework import sparse_tensor
from tensorflow.python.framework import tensor_shape
from tensorflow.python.framework import tensor_spec
from tensorflow.python.framework import test_util
from tensorflow.python.ops import array_ops
from tensorflow.python.ops.ragged import ragged_factory_ops
from tensorflow.python.ops.ragged import ragged_tensor
from tensorflow.python.ops.ragged import row_partition
from tensorflow.python.ops.structured import structured_tensor
from tensorflow.python.ops.structured.structured_tensor import StructuredTensor
from tensorflow.python.platform import googletest


# pylint: disable=g-long-lambda
@test_util.run_all_in_graph_and_eager_modes
class StructuredTensorTest(test_util.TensorFlowTestCase,
                           parameterized.TestCase):

  def assertAllEqual(self, a, b, msg=None):
    if not (isinstance(a, structured_tensor.StructuredTensor) or
            isinstance(b, structured_tensor.StructuredTensor)):
      return super(StructuredTensorTest, self).assertAllEqual(a, b, msg)
    if not isinstance(a, structured_tensor.StructuredTensor):
      a = structured_tensor.StructuredTensor.from_pyval(a)
      self._assertStructuredEqual(a, b, msg, False)
    elif not isinstance(b, structured_tensor.StructuredTensor):
      b = structured_tensor.StructuredTensor.from_pyval(b)
      self._assertStructuredEqual(a, b, msg, False)
    else:
      self._assertStructuredEqual(a, b, msg, True)

  def _assertStructuredEqual(self, a, b, msg, check_shape):
    if check_shape:
      self.assertEqual(repr(a.shape), repr(b.shape))
    self.assertEqual(set(a.field_names()), set(b.field_names()))
    for field in a.field_names():
      a_value = a.field_value(field)
      b_value = b.field_value(field)
      self.assertIs(type(a_value), type(b_value))
      if isinstance(a_value, structured_tensor.StructuredTensor):
        self._assertStructuredEqual(a_value, b_value, msg, check_shape)
      else:
        self.assertAllEqual(a_value, b_value, msg)

  def testConstructorIsPrivate(self):
    with self.assertRaisesRegexp(ValueError,
                                 "StructuredTensor constructor is private"):
      structured_tensor.StructuredTensor({}, (), None, ())

  @parameterized.named_parameters([
      # Scalar (rank=0) StructuredTensors.
      {
          "testcase_name": "Rank0_WithNoFields",
          "shape": [],
          "fields": {},
      },
      {
          "testcase_name": "Rank0_WithTensorFields",
          "shape": [],
          "fields": {"Foo": 5, "Bar": [1, 2, 3]},
      },
      {
          "testcase_name": "Rank0_WithRaggedFields",
          "shape": [],
          "fields": {
              # note: fields have varying rank & ragged_rank.
              "p": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "q": ragged_factory_ops.constant_value([[[4]], [], [[5, 6]]]),
              "r": ragged_factory_ops.constant_value([[[4]], [], [[5]]],
                                                     ragged_rank=1),
              "s": ragged_factory_ops.constant_value([[[4]], [], [[5]]],
                                                     ragged_rank=2),
          },
      },
      {
          "testcase_name": "Rank0_WithStructuredFields",
          "shape": [],
          "fields": lambda: {
              "foo": StructuredTensor.from_pyval({"a": 1, "b": [1, 2, 3]}),
              "bar": StructuredTensor.from_pyval(
                  [[{"x": 12}], [{"x": 13}, {"x": 14}]]),
              },
      },
      {
          "testcase_name": "Rank0_WithMixedFields",
          "shape": [],
          "fields": lambda: {
              "f1": 5,
              "f2": [1, 2, 3],
              "f3": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "f4": StructuredTensor.from_pyval({"a": 1, "b": [1, 2, 3]}),
          },
      },
      # Vector (rank=1) StructuredTensors.
      {
          "testcase_name": "Rank1_WithNoFields",
          "shape": [2],
          "fields": {},
      },
      {
          "testcase_name": "Rank1_WithExplicitNrows",
          "shape": [None],
          "nrows": 2,
          "fields": {"x": [1, 2], "y": [[1, 2], [3, 4]]},
          "expected_shape": [2],
      },
      {
          "testcase_name": "Rank1_WithTensorFields",
          "shape": [2],
          "fields": {"x": [1, 2], "y": [[1, 2], [3, 4]]},
      },
      {
          "testcase_name": "Rank1_WithRaggedFields",
          "shape": [2],
          "fields": {
              # note: fields have varying rank & ragged_rank.
              "p": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "q": ragged_factory_ops.constant_value([[[4]], [[5, 6], [7]]]),
              "r": ragged_factory_ops.constant_value([[], [[[12]], [[13]]]]),
              "s": ragged_factory_ops.constant_value([[], [[[12]], [[13]]]],
                                                     ragged_rank=1),
              "t": ragged_factory_ops.constant_value([[], [[[12]], [[13]]]],
                                                     ragged_rank=2),
          },
      },
      {
          "testcase_name": "Rank1_WithStructuredFields",
          "shape": [2],
          "fields": lambda: {
              "foo": StructuredTensor.from_pyval(
                  [{"a": 1, "b": [1, 2, 3]}, {"a": 2, "b": []}]),
              "bar": StructuredTensor.from_pyval(
                  [[{"x": 12}], [{"x": 13}, {"x": 14}]]),
          },
      },
      {
          "testcase_name": "Rank1_WithMixedFields",
          "shape": [2],
          "fields": lambda: {
              "x": [1, 2],
              "y": [[1, 2], [3, 4]],
              "r": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "s": StructuredTensor.from_pyval(
                  [[{"x": 12}], [{"x": 13}, {"x": 14}]]),
          },
      },
      {
          "testcase_name": "Rank1_WithNoElements",
          "shape": [0],
          "fields": lambda: {
              "x": [],
              "y": np.zeros([0, 8]),
              "r": ragged_factory_ops.constant([], ragged_rank=1),
              "s": StructuredTensor.from_pyval([]),
          },
      },
      {
          "testcase_name": "Rank1_InferDimSize",
          "shape": [None],
          "fields": lambda: {
              "x": [1, 2],
              "y": [[1, 2], [3, 4]],
              "r": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "p": ragged_factory_ops.constant_value([[4], [5, 6, 7]]),
              "foo": StructuredTensor.from_pyval(
                  [{"a": 1, "b": [1, 2, 3]}, {"a": 2, "b": []}]),
              "bar": StructuredTensor.from_pyval(
                  [[{"x": 12}], [{"x": 13}, {"x": 14}]]),
          },
          "expected_shape": [2],  # inferred from field values.
      },
      # Matrix (rank=2) StructuredTensors.
      {
          "testcase_name": "Rank2_WithNoFields",
          "shape": [2, 8],
          "fields": {},
      },
      {
          "testcase_name": "Rank2_WithNoFieldsAndExplicitRowPartitions",
          "shape": [2, None],
          "row_partitions":
              lambda: [row_partition.RowPartition.from_row_lengths([3, 7])],
          "fields": {},
      },
      {
          "testcase_name": "Rank2_WithTensorFields",
          "shape": [None, None],
          "fields": {
              "x": [[1, 2, 3], [4, 5, 6]],
              "y": np.ones([2, 3, 8])
          },
          "expected_shape": [2, 3],  # inferred from field values.
      },
      {
          "testcase_name": "Rank2_WithRaggedFields",
          "shape": [2, None],  # ragged shape = [[*, *], [*]]
          "fields": {
              # Note: fields must have identical row_splits.
              "a": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "b": ragged_factory_ops.constant_value([[4, 5], [6]]),
              "c": ragged_factory_ops.constant_value([[[1, 2], [3]], [[4, 5]]]),
              "d": ragged_factory_ops.constant_value(
                  [[[[1, 2], [3]], [[4], [], [5]]], [[[6, 7, 8], []]]]),
          },
      },
      {
          "testcase_name": "Rank2_WithStructuredFields",
          "shape": [2, None],  # ragged shape = [[*], [*, *]]
          "fields": lambda: {
              # Note: fields must have identical row_splits.
              "a": StructuredTensor.from_pyval(
                  [[{"x": 1}], [{"x": 2}, {"x": 3}]]),
              "b": StructuredTensor.from_pyval(
                  [[[{"y": 1}]], [[], [{"y": 2}, {"y": 3}]]]),
          },
      },
      {
          "testcase_name": "Rank2_WithMixedFields",
          "shape": [2, None],
          "fields": lambda: {
              "a": [[1, 2], [3, 4]],
              "b": ragged_factory_ops.constant_value([[1, 2], [3, 4]]),
              "c": StructuredTensor.from_pyval(
                  [[[{"y": 1}], []], [[], [{"y": 2}, {"y": 3}]]]),
              "d": ragged_factory_ops.constant_value(
                  [[[1, 2], []], [[3], [4]]]),
          },
          "expected_shape": [2, 2],
      },
      # Rank=4 StructuredTensors.
      {
          "testcase_name": "Rank4_WithNoFields",
          "shape": [1, None, None, 3],
          "fields": {},
          "row_partitions": lambda: [
              row_partition.RowPartition.from_row_lengths([3]),
              row_partition.RowPartition.from_row_lengths([2, 0, 1]),
              row_partition.RowPartition.from_uniform_row_length(3, nvals=9)
          ]
      },
      {
          "testcase_name": "Rank4_WithMixedFields",
          "shape": [1, None, None, 1],
          "fields": lambda: {
              "a": np.ones([1, 2, 3, 1]),
              "b": np.ones([1, 2, 3, 1, 5]),
              "c": ragged_factory_ops.constant(np.zeros([1, 2, 3, 1])),
              "d": ragged_factory_ops.constant(
                  np.zeros([1, 2, 3, 1, 3]).tolist(), ragged_rank=1),
              "e": ragged_factory_ops.constant(
                  np.zeros([1, 2, 3, 1, 2, 2]).tolist(), ragged_rank=2),
              "f": ragged_factory_ops.constant(np.zeros([1, 2, 3, 1, 3])),
              "g": StructuredTensor.from_pyval(
                  [[[[{"x": j, "y": k}] for k in range(3)]
                    for j in range(2)]]),
              "h": StructuredTensor.from_pyval(
                  [[[[[{"x": j, "y": k, "z": z} for z in range(j)]]
                     for k in range(3)]
                    for j in range(2)]]),
          },
          "expected_shape": [1, 2, 3, 1],  # inferred from field values.
      },
  ])  # pyformat: disable
  def testFromFields(self,
                     shape,
                     fields,
                     expected_shape=None,
                     nrows=None,
                     row_partitions=None):
    if callable(fields):
      fields = fields()  # deferred construction: fields may include tensors.
    if callable(nrows):
      nrows = nrows()  # deferred construction.
    if callable(row_partitions):
      row_partitions = row_partitions()  # deferred construction.
    for validate in (True, False):
      struct = StructuredTensor.from_fields(
          fields,
          shape,
          nrows=nrows,
          row_partitions=row_partitions,
          validate=validate)
      if expected_shape is None:
        expected_shape = shape
      self.assertEqual(struct.shape.as_list(), expected_shape)
      self.assertLen(expected_shape, struct.rank)
      self.assertCountEqual(struct.field_names(), tuple(fields.keys()))
      for field, value in fields.items():
        self.assertIsInstance(
            struct.field_value(field),
            (ops.Tensor, structured_tensor.StructuredTensor,
             ragged_tensor.RaggedTensor))
        self.assertAllEqual(struct.field_value(field), value)

  @parameterized.parameters([
      dict(fields={}, shape=object(), err=TypeError),
      dict(
          fields=object(),
          shape=[],
          err=TypeError,
          msg="fields must be a dictionary"),
      dict(
          fields={1: 2}, shape=[], err=TypeError,
          msg="Unexpected type for key"),
      dict(
          fields={"x": object()},
          shape=[],
          err=TypeError,
          msg="Unexpected type for value"),
      dict(
          fields={},
          shape=None,
          err=ValueError,
          msg="StructuredTensor's shape must have known rank"),
      dict(
          fields={"f": 5},
          shape=[5],
          err=ValueError,
          msg=r"Field f has shape \(\), which is incompatible with the shape "
          r"that was specified or inferred from other fields: \(5,\)"),
      dict(
          fields=dict(x=[1], y=[]),
          shape=[None],
          err=ValueError,
          msg=r"Field . has shape .*, which is incompatible with the shape "
          r"that was specified or inferred from other fields: .*"),
      dict(
          fields={"": 5},
          shape=[],
          err=ValueError,
          msg="Field name '' is not currently allowed."),
      dict(
          fields={"_": 5},
          shape=[],
          err=ValueError,
          msg="Field name '_' is not currently allowed."),
      dict(
          fields={
              "r1": ragged_factory_ops.constant_value([[1, 2], [3]]),
              "r2": ragged_factory_ops.constant_value([[1, 2, 3], [4]])
          },
          shape=[2, None],
          validate=True,
          err=errors.InvalidArgumentError,
          msg=r"incompatible row_splits",
      ),
      dict(
          fields={},
          shape=(),
          nrows=5,
          err=ValueError,
          msg="nrows must be None if shape.rank==0"),
      dict(
          fields={},
          shape=(),
          row_partitions=[0],
          err=ValueError,
          msg=r"row_partitions must be None or \[\] if shape.rank<2"),
      dict(
          fields={},
          shape=(None, None, None),
          row_partitions=[],
          err=ValueError,
          msg=r"len\(row_partitions\) must be shape.rank-1"),
      dict(
          fields={},
          shape=[None],
          err=ValueError,
          msg="nrows must be specified if rank==1 and `fields` is empty."),
      dict(
          fields={},
          shape=[None, None],
          err=ValueError,
          msg="row_partitions must be specified if rank>1 and `fields` "
          "is empty."),
      dict(
          fields={},
          shape=[None, None],
          nrows=lambda: constant_op.constant(2, dtypes.int32),
          row_partitions=lambda:
          [row_partition.RowPartition.from_row_lengths([3, 4])],
          err=ValueError,
          msg="field values have incompatible row_partition dtypes"),
      dict(
          fields=lambda: {
              "a":
                  ragged_factory_ops.constant([[1]],
                                              row_splits_dtype=dtypes.int32),
              "b":
                  ragged_factory_ops.constant([[1]],
                                              row_splits_dtype=dtypes.int64)
          },
          shape=[None, None],
          err=ValueError,
          msg="field values have incompatible row_partition dtypes"),
      dict(
          fields=lambda: {
              "a":
                  array_ops.placeholder_with_default(np.array([1, 2, 3]), None),
              "b":
                  array_ops.placeholder_with_default(np.array([4, 5]), None)
          },
          validate=True,
          shape=[None],
          err=(ValueError, errors.InvalidArgumentError),
          msg="fields have incompatible nrows",
          test_in_eager=False),
  ])
  def testFromFieldsErrors(self,
                           fields,
                           shape,
                           nrows=None,
                           row_partitions=None,
                           validate=False,
                           err=ValueError,
                           msg=None,
                           test_in_eager=True):
    if not test_in_eager and context.executing_eagerly():
      return
    if callable(fields):
      fields = fields()  # deferred construction.
    if callable(nrows):
      nrows = nrows()  # deferred construction.
    if callable(row_partitions):
      row_partitions = row_partitions()  # deferred construction.
    with self.assertRaisesRegexp(err, msg):
      struct = StructuredTensor.from_fields(
          fields=fields,
          shape=shape,
          nrows=nrows,
          row_partitions=row_partitions,
          validate=validate)
      for field_name in struct.field_names():
        self.evaluate(struct.field_value(field_name))
      self.evaluate(struct.nrows())

  def testMergeNrowsErrors(self):
    nrows = constant_op.constant(5)
    static_nrows = tensor_shape.Dimension(5)
    value = constant_op.constant([1, 2, 3])
    with self.assertRaisesRegexp(ValueError, "fields have incompatible nrows"):
      structured_tensor._merge_nrows(nrows, static_nrows, value, dtypes.int32,
                                     validate=False)

  def testNestedStructConstruction(self):
    rt = ragged_factory_ops.constant([[1, 2], [3]])
    struct1 = StructuredTensor.from_fields(shape=[], fields={"x": [1, 2]})
    struct2 = StructuredTensor.from_fields(shape=[2], fields={"x": [1, 2]})
    struct3 = StructuredTensor.from_fields(
        shape=[], fields={
            "r": rt,
            "s": struct1
        })
    struct4 = StructuredTensor.from_fields(
        shape=[2], fields={
            "r": rt,
            "s": struct2
        })

    self.assertEqual(struct3.shape.as_list(), [])
    self.assertEqual(struct3.rank, 0)
    self.assertEqual(set(struct3.field_names()), set(["r", "s"]))
    self.assertAllEqual(struct3.field_value("r"), rt)
    self.assertAllEqual(struct3.field_value("s"), struct1)

    self.assertEqual(struct4.shape.as_list(), [2])
    self.assertEqual(struct4.rank, 1)
    self.assertEqual(set(struct4.field_names()), set(["r", "s"]))
    self.assertAllEqual(struct4.field_value("r"), rt)
    self.assertAllEqual(struct4.field_value("s"), struct2)

  def testPartitionOuterDims(self):
    if not context.executing_eagerly(): return  # TESTING
    a = dict(x=1, y=[1, 2])
    b = dict(x=2, y=[3, 4])
    c = dict(x=3, y=[5, 6])
    d = dict(x=4, y=[7, 8])
    st1 = StructuredTensor.from_pyval([a, b, c, d])

    st2 = st1.partition_outer_dimension(
        row_partition.RowPartition.from_row_splits([0, 2, 2, 3, 4]))
    self.assertAllEqual(st2, [[a, b], [], [c], [d]])

    st3 = st2.partition_outer_dimension(
        row_partition.RowPartition.from_row_lengths([1, 0, 3, 0]))
    self.assertAllEqual(st3, [[[a, b]], [], [[], [c], [d]], []])

    # If we partition with uniform_row_lengths, then `x` is partitioned into
    # a Tensor (not a RaggedTensor).
    st4 = st1.partition_outer_dimension(
        row_partition.RowPartition.from_uniform_row_length(
            uniform_row_length=2, nvals=4, nrows=2))
    self.assertAllEqual(st4, structured_tensor.StructuredTensor.from_pyval(
        [[a, b], [c, d]], structured_tensor.StructuredTensorSpec([2, 2], {
            "x": tensor_spec.TensorSpec([2, 2], dtypes.int32),
            "y": ragged_tensor.RaggedTensorSpec([2, 2, None], dtypes.int32)})))

  def testPartitionOuterDimsErrors(self):
    st = StructuredTensor.from_fields({})
    partition = row_partition.RowPartition.from_row_splits([0])
    with self.assertRaisesRegexp(ValueError,
                                 r"Shape \(\) must have rank at least 1"):
      st.partition_outer_dimension(partition)

    with self.assertRaisesRegexp(TypeError,
                                 "row_partition must be a RowPartition"):
      st.partition_outer_dimension(10)

  @parameterized.named_parameters([
      {
          "testcase_name": "ScalarEmpty",
          "pyval": {},
          "expected": lambda: StructuredTensor.from_fields(shape=[], fields={})
      },
      {
          "testcase_name": "ScalarSimple",
          "pyval": {"a": 12, "b": [1, 2, 3], "c": [[1, 2], [3]]},
          "expected": lambda: StructuredTensor.from_fields(shape=[], fields={
              "a": 12,
              "b": [1, 2, 3],
              "c": ragged_factory_ops.constant([[1, 2], [3]])})
      },
      {
          "testcase_name": "ScalarSimpleWithTypeSpec",
          "pyval": {"a": 12, "b": [1, 2, 3], "c": [[1, 2], [3]]},
          "type_spec": structured_tensor.StructuredTensorSpec([], {
              "a": tensor_spec.TensorSpec([], dtypes.int32),
              "b": tensor_spec.TensorSpec([None], dtypes.int32),
              "c": ragged_tensor.RaggedTensorSpec([None, None], dtypes.int32)}),
          "expected": lambda: StructuredTensor.from_fields(shape=[], fields={
              "a": 12,
              "b": [1, 2, 3],
              "c": ragged_factory_ops.constant([[1, 2], [3]])})
      },
      {
          "testcase_name": "ScalarWithNestedStruct",
          "pyval": {"a": 12, "b": [1, 2, 3], "c": {"x": b"Z", "y": [10, 20]}},
          "expected": lambda: StructuredTensor.from_fields(shape=[], fields={
              "a": 12,
              "b": [1, 2, 3],
              "c": StructuredTensor.from_fields(shape=[], fields={
                  "x": "Z",
                  "y": [10, 20]})})
      },
      {
          "testcase_name": "EmptyList",
          "pyval": [],
          "expected": lambda: [],
      },
      {
          "testcase_name": "ListOfEmptyList",
          "pyval": [[], []],
          "expected": lambda: [[], []],
      },
      {
          "testcase_name": "EmptyListWithTypeSpecAndFields",
          "pyval": [],
          "type_spec": structured_tensor.StructuredTensorSpec([0], {
              "a": tensor_spec.TensorSpec(None, dtypes.int32)}),
          "expected": lambda: StructuredTensor.from_fields(shape=[0], fields={
              "a": []})
      },
      {
          "testcase_name": "EmptyListWithTypeSpecNoFieldsShape0_5",
          "pyval": [],
          "type_spec": structured_tensor.StructuredTensorSpec([0, 5], {}),
          "expected": lambda: StructuredTensor.from_fields(shape=[0, 5],
                                                           fields={})
      },
      {
          "testcase_name": "EmptyListWithTypeSpecNoFieldsShape1_0",
          "pyval": [[]],
          "type_spec": structured_tensor.StructuredTensorSpec([1, 0], {}),
          "expected": lambda: StructuredTensor.from_fields(shape=[1, 0],
                                                           fields={})
      },
      {
          "testcase_name": "VectorOfDict",
          "pyval": [{"a": 1}, {"a": 2}],
          "expected": lambda: StructuredTensor.from_fields(shape=[2], fields={
              "a": [1, 2]})
      },
      {
          "testcase_name": "VectorOfDictWithNestedStructScalar",
          "pyval": [{"a": 1, "b": {"x": [1, 2]}},
                    {"a": 2, "b": {"x": [3]}}],
          "expected": lambda: StructuredTensor.from_fields(shape=[2], fields={
              "a": [1, 2],
              "b": StructuredTensor.from_fields(shape=[2], fields={
                  "x": ragged_factory_ops.constant([[1, 2], [3]])})}),
      },
      {
          "testcase_name": "VectorOfDictWithNestedStructVector",
          "pyval": [{"a": 1, "b": [{"x": [1, 2]}, {"x": [5]}]},
                    {"a": 2, "b": [{"x": [3]}]}],
          "expected": lambda: StructuredTensor.from_fields(shape=[2], fields={
              "a": [1, 2],
              "b": StructuredTensor.from_fields(shape=[2, None], fields={
                  "x": ragged_factory_ops.constant([[[1, 2], [5]], [[3]]])})}),
      },
      {
          "testcase_name": "Ragged2DOfDict",
          "pyval": [[{"a": 1}, {"a": 2}, {"a": 3},],
                    [{"a": 4}, {"a": 5}]],
          "expected": lambda: StructuredTensor.from_fields(
              shape=[2, None],
              fields={
                  "a": ragged_factory_ops.constant([[1, 2, 3], [4, 5]])})
      },
      {
          # With no type-spec, all tensors>1D are encoded as ragged:
          "testcase_name": "MatrixOfDictWithoutTypeSpec",
          "pyval": [[{"a": 1}, {"a": 2}, {"a": 3},],
                    [{"a": 4}, {"a": 5}, {"a": 6}]],
          "expected": lambda: StructuredTensor.from_fields(
              shape=[2, None], fields={
                  "a": ragged_factory_ops.constant([[1, 2, 3], [4, 5, 6]])})
      },
      {
          # TypeSpec can be used to specify StructuredTensor shape.
          "testcase_name": "MatrixOfDictWithTypeSpec",
          "pyval": [[{"a": 1}, {"a": 2}, {"a": 3},],
                    [{"a": 4}, {"a": 5}, {"a": 6}]],
          "type_spec": structured_tensor.StructuredTensorSpec([2, 3], {
              "a": tensor_spec.TensorSpec(None, dtypes.int32)}),
          "expected": lambda: StructuredTensor.from_fields(
              shape=[2, 3], fields={"a": [[1, 2, 3], [4, 5, 6]]})
      },
  ])  # pyformat: disable
  def testPyvalConversion(self, pyval, expected, type_spec=None):
    expected = expected()  # Deferred init because it creates tensors.
    actual = structured_tensor.StructuredTensor.from_pyval(pyval, type_spec)
    self.assertAllEqual(actual, expected)
    if isinstance(actual, structured_tensor.StructuredTensor):
      if context.executing_eagerly():  # to_pyval only available in eager.
        self.assertEqual(actual.to_pyval(), pyval)

  @parameterized.named_parameters([
      dict(testcase_name="MissingKeys",
           pyval=[{"a": [1, 2]}, {"b": [3, 4]}],
           err=KeyError,
           msg="'b'"),
      dict(testcase_name="TypeSpecMismatch_DictKey",
           pyval={"a": 1},
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[1],
               field_specs={"b": tensor_spec.TensorSpec([], dtypes.int32)}),
           msg="Value does not match typespec"),
      dict(testcase_name="TypeSpecMismatch_ListDictKey",
           pyval=[{"a": 1}],
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[1],
               field_specs={"b": tensor_spec.TensorSpec([], dtypes.int32)}),
           msg="Value does not match typespec"),
      dict(testcase_name="TypeSpecMismatch_RankMismatch",
           pyval=[{"a": 1}],
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[],
               field_specs={"a": tensor_spec.TensorSpec([], dtypes.int32)}),
           msg=r"Value does not match typespec \(rank mismatch\)"),
      dict(testcase_name="TypeSpecMismatch_Scalar",
           pyval=0,
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[], field_specs={}),
           msg="Value does not match typespec"),
      dict(testcase_name="TypeSpecMismatch_ListTensor",
           pyval={"a": [[1]]},
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[],
               field_specs={"a": tensor_spec.TensorSpec([], dtypes.int32)}),
           msg="Value does not match typespec"),
      dict(testcase_name="TypeSpecMismatch_ListSparse",
           pyval=[1, 2],
           type_spec=sparse_tensor.SparseTensorSpec([None], dtypes.int32),
           msg="Value does not match typespec"),
      dict(testcase_name="TypeSpecMismatch_ListStruct",
           pyval=[[1]],
           type_spec=structured_tensor.StructuredTensorSpec(
               shape=[1, 1],
               field_specs={"a": tensor_spec.TensorSpec([], dtypes.int32)}),
           msg="Value does not match typespec"),
      dict(testcase_name="InconsistentDictionaryDepth",
           pyval=[{}, [{}]],
           msg="Inconsistent depth of dictionaries"),
      dict(testcase_name="FOO",
           pyval=[[{}], 5],
           msg="Expected dict or nested list/tuple of dict"),

  ])  # pyformat: disable
  def testFromPyvalError(self, pyval, err=ValueError, type_spec=None, msg=None):
    with self.assertRaisesRegexp(err, msg):
      structured_tensor.StructuredTensor.from_pyval(pyval, type_spec)

  def testToPyvalRequiresEagerMode(self):
    st = structured_tensor.StructuredTensor.from_pyval({"a": 5})
    if not context.executing_eagerly():
      with self.assertRaisesRegexp(ValueError, "only supported in eager mode."):
        st.to_pyval()

  @parameterized.named_parameters([
      (
          "Rank0",
          [],
      ),
      (
          "Rank1",
          [5, 3],
      ),
      (
          "Rank2",
          [5, 8, 3],
      ),
      (
          "Rank5",
          [1, 2, 3, 4, 5],
      ),
  ])
  def testRowPartitionsFromUniformShape(self, shape):
    for rank in range(len(shape)):
      partitions = structured_tensor._row_partitions_for_uniform_shape(
          ops.convert_to_tensor(shape), rank)
      self.assertLen(partitions, max(0, rank - 1))
      if partitions:
        self.assertAllEqual(shape[0], partitions[0].nrows())
      for (dim, partition) in enumerate(partitions):
        self.assertAllEqual(shape[dim + 1], partition.uniform_row_length())

  @parameterized.named_parameters([
      # For shapes: U = uniform dimension; R = ragged dimension.
      dict(
          testcase_name="Shape_UR_Rank2",
          rt=[[1, 2], [], [3]],
          rt_ragged_rank=1,
          rank=2,
          expected_row_lengths=[[2, 0, 1]]),
      dict(
          testcase_name="Shape_URR_Rank2",
          rt=[[[1, 2], []], [[3]]],
          rt_ragged_rank=2,
          rank=2,
          expected_row_lengths=[[2, 1]]),
      dict(
          testcase_name="Shape_URU_Rank2",
          rt=[[[1], [2]], [[3]]],
          rt_ragged_rank=1,
          rank=2,
          expected_row_lengths=[[2, 1]]),
      dict(
          testcase_name="Shape_URR_Rank3",
          rt=[[[1, 2], []], [[3]]],
          rt_ragged_rank=2,
          rank=3,
          expected_row_lengths=[[2, 1], [2, 0, 1]]),
      dict(
          testcase_name="Shape_URU_Rank3",
          rt=[[[1], [2]], [[3]]],
          rt_ragged_rank=1,
          rank=3,
          expected_row_lengths=[[2, 1], [1, 1, 1]]),
      dict(
          testcase_name="Shape_URRUU_Rank2",
          rt=[[[[[1, 2]]]]],
          rt_ragged_rank=2,
          rank=2,
          expected_row_lengths=[[1]]),
      dict(
          testcase_name="Shape_URRUU_Rank3",
          rt=[[[[[1, 2]]]]],
          rt_ragged_rank=2,
          rank=3,
          expected_row_lengths=[[1], [1]]),
      dict(
          testcase_name="Shape_URRUU_Rank4",
          rt=[[[[[1, 2]]]]],
          rt_ragged_rank=2,
          rank=4,
          expected_row_lengths=[[1], [1], [1]]),
      dict(
          testcase_name="Shape_URRUU_Rank5",
          rt=[[[[[1, 2]]]]],
          rt_ragged_rank=2,
          rank=5,
          expected_row_lengths=[[1], [1], [1], [2]]),
  ])
  def testRowPartitionsForRaggedTensor(self, rt, rt_ragged_rank, rank,
                                       expected_row_lengths):
    rt = ragged_factory_ops.constant(rt, rt_ragged_rank)
    partitions = structured_tensor._row_partitions_for_ragged_tensor(
        rt, rank, dtypes.int64)
    self.assertLen(partitions, rank - 1)
    self.assertLen(partitions, len(expected_row_lengths))
    for partition, expected in zip(partitions, expected_row_lengths):
      self.assertAllEqual(partition.row_lengths(), expected)

  @parameterized.named_parameters([
      dict(
          testcase_name="2D_0_1",
          st=[[{"x": 1}, {"x": 2}], [{"x": 3}]],
          outer_axis=0, inner_axis=1,
          expected=[{"x": 1}, {"x": 2}, {"x": 3}]),
      dict(
          testcase_name="3D_0_1",
          st=[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
          outer_axis=0, inner_axis=1,
          expected=[[{"x": 1}, {"x": 2}], [{"x": 3}], [{"x": 4}]]),
      dict(
          testcase_name="3D_1_2",
          st=[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
          outer_axis=1, inner_axis=2,
          expected=[[{"x": 1}, {"x": 2}, {"x": 3}], [{"x": 4}]]),
      dict(
          testcase_name="3D_0_2",
          st=[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
          outer_axis=0, inner_axis=2,
          expected=[{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}]),
      dict(
          testcase_name="4D_0_1",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=0, inner_axis=1,
          expected=[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]],
                    [[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]),
      dict(
          testcase_name="4D_0_2",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=0, inner_axis=2,
          expected=[[{"x": 1}, {"x": 2}], [{"x": 3}], [{"x": 4}],
                    [{"x": 5}], [{"x": 6}], [{"x": 7}]]),
      dict(
          testcase_name="4D_0_3",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=0, inner_axis=3,
          expected=[{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4},
                    {"x": 5}, {"x": 6}, {"x": 7}]),
      dict(
          testcase_name="4D_1_2",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=1, inner_axis=2,
          expected=[[[{"x": 1}, {"x": 2}], [{"x": 3}], [{"x": 4}]],
                    [[{"x": 5}], [{"x": 6}], [{"x": 7}]]]),
      dict(
          testcase_name="4D_1_3",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=1, inner_axis=3,
          expected=[[{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}],
                    [{"x": 5}, {"x": 6}, {"x": 7}]]),
      dict(
          testcase_name="4D_2_3",
          st=[[[[{"x": 1}, {"x": 2}], [{"x": 3}]], [[{"x": 4}]]],
              [[[{"x": 5}]], [[{"x": 6}], [{"x": 7}]]]],
          outer_axis=2, inner_axis=3,
          expected=[[[{"x": 1}, {"x": 2}, {"x": 3}], [{"x": 4}]],
                    [[{"x": 5}], [{"x": 6}, {"x": 7}]]]),
  ])  # pyformat: disable
  def testMergeDims(self, st, outer_axis, inner_axis, expected):
    st = StructuredTensor.from_pyval(st)
    result = st.merge_dims(outer_axis, inner_axis)
    self.assertAllEqual(result, expected)

  def testMergeDimsError(self):
    st = StructuredTensor.from_pyval([[[{"a": 5}]]])
    with self.assertRaisesRegexp(
        ValueError,
        r"Expected outer_axis \(2\) to be less than inner_axis \(1\)"):
      st.merge_dims(2, 1)

  def testTupleFieldValue(self):
    st = StructuredTensor.from_pyval({"a": 5, "b": {"c": [1, 2, 3]}})
    self.assertAllEqual(st.field_value(("a",)), 5)
    self.assertAllEqual(st.field_value(("b", "c")), [1, 2, 3])
    expected = "Field path \(.*a.*,.*b.*\) not found in .*"
    with self.assertRaisesRegexp(KeyError, expected):
      st.field_value(("a", "b"))

  def testRepr(self):
    st = StructuredTensor.from_pyval({"a": 5, "b": {"c": [1, 2, 3]}})
    if context.executing_eagerly():
      expected = ('<StructuredTensor(fields={'
                  '"a": tf.Tensor(5, shape=(), dtype=int32), '
                  '"b": <StructuredTensor(fields={'
                  '"c": tf.Tensor([1 2 3], shape=(3,), dtype=int32)}, '
                  'shape=())>}, shape=())>')
    else:
      expected = ('<StructuredTensor(fields={'
                  '"a": Tensor("Const:0", shape=(), dtype=int32), '
                  '"b": <StructuredTensor(fields={'
                  '"c": Tensor("RaggedConstant/Const:0", shape=(3,), '
                  'dtype=int32)}, shape=())>}, shape=())>')
    self.assertEqual(repr(st), expected)


if __name__ == "__main__":
  googletest.main()
