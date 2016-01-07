# -*- coding: utf-8 -*-
"""
Created on Wed Jan  6 14:00:34 2016

Based on http://stackoverflow.com/questions/3488934/simplejson-and-numpy-array/24375113#24375113

@author: tlausch
@author: Def_Os
"""

import base64
import json
import numpy as np
from numpy.lib.stride_tricks import as_strided


class NumpyEncoder(json.JSONEncoder):

    def default(self, obj):
        """If input object is an ndarray it will be converted into a dict
        holding dtype, shape and the data, base64 encoded.
        """
        if isinstance(obj, np.ndarray):
            data_b64 = base64.b64encode(obj.flatten('A'))
            return dict(__ndarray__=str(data_b64, 'ascii'),
                        dtype=str(obj.dtype),
                        shape=obj.shape,
                        strides=obj.strides)
        elif isinstance(obj, np.generic):
            return obj.item()

        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def json_numpy_obj_hook(dct):
    """Decodes a previously encoded numpy ndarray with proper shape and dtype.

    :param dct: (dict) json encoded ndarray
    :return: (ndarray) if input was an encoded ndarray
    """
    if isinstance(dct, dict) and '__ndarray__' in dct:
        data = base64.b64decode(dct['__ndarray__'])
        return as_strided(np.frombuffer(data, dct['dtype']),
                          shape=dct['shape'], strides=dct['strides'])
    return dct

if __name__ == '__main__':
    expected = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
    dumped = json.dumps(expected, cls=NumpyEncoder)
    result = json.loads(dumped, object_hook=json_numpy_obj_hook)

    print("Expected:\n{}\n - {}".format(str(expected), expected.flags))
    print("Result:\n{}\n - {}".format(str(result), result.flags))

    # None of the following assertions will be broken.
    assert result.dtype == expected.dtype, "Wrong Type"
    assert result.shape == expected.shape, "Wrong Shape"
    assert np.allclose(expected, result), "Wrong Values"
