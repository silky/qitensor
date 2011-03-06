import numpy as np

from qitensor.exceptions import *
from qitensor.space import *

class HilbertAtom(HilbertSpace):
    def __init__(self, label, latex_label, indices, base_field, dual=None):
        is_dual = not dual is None

        self.indices = indices
        self.label = label
        if latex_label is None:
            latex_label = label
        self.latex_label = latex_label
        self.is_dual = is_dual

        self._prime = None

        self._hashval = hash(self.label)
        if self.is_dual:
            self._hashval += 1

        HilbertSpace.__init__(self, None, None, base_field)

        ket_shape = [len(x.indices) for x in self.sorted_kets]
        bra_shape = [len(x.indices) for x in self.sorted_bras]
        self.shape = tuple(ket_shape + bra_shape)

        if dual:
            self._H = dual
        else:
            self._H = HilbertAtom(label, latex_label,
                indices, base_field, self)

    def __cmp__(self, other):
        if not isinstance(other, HilbertAtom):
            return HilbertSpace.__cmp__(self, other)
        else:
            if self.label < other.label:
                return -1
            elif self.label > other.label:
                return 1

            # It is not allowed for HilbertAtom's to have the same name but
            # different index set
            if self.indices != other.indices:
                raise MismatchedIndexSetError('Two instances of HilbertSpace '+
                    'with label "'+repr(self.label)+'" but with different '+
                    'indices: '+repr(self.indices)+' vs. '+repr(other.indices))

            if self.is_dual < other.is_dual:
                return -1
            elif self.is_dual > other.is_dual:
                return 1
            else:
                return 0

    def __hash__(self):
        return self._hashval

    @property
    def prime(self):
        """
        Returns a ``HilbertAtom`` just like this one but with an apostrophe
        appended to the label.

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.prime
        |a'>
        >>> ha.prime.prime
        |a''>
        """
        if self._prime is None:
            if self.is_dual:
                self._prime = self.H.prime.H
            else:
                self._prime = self.base_field.indexed_space(
                    self.label+"'", self.indices, "{"+self.latex_label+"}'")
        return self._prime

    def bra(self, idx):
        """
        Returns a bra basis vector.

        The returned vector has a 1 in the slot corresponding to ``idx`` and
        zeros elsewhere.

        :param idx: a member of this space's index set

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> hx = indexed_space('x', ['x', 'y', 'z'])

        >>> ha.bra(0)
        HilbertArray(|a>,
        array([ 1.+0.j,  0.+0.j]))

        >>> hx.bra('y')
        HilbertArray(|x>,
        array([ 0.+0.j,  1.+0.j,  0.+0.j]))
        """

        if self.is_dual:
            return self.H.basis_vec({self.H: idx})
        else:
            return self.basis_vec({self: idx})

    def ket(self, idx):
        """
        Returns a ket basis vector.

        The returned vector has a 1 in the slot corresponding to ``idx`` and
        zeros elsewhere.

        :param idx: a member of this space's index set

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> hx = indexed_space('x', ['x', 'y', 'z'])

        >>> ha.ket(0)
        HilbertArray(<a|,
        array([ 1.+0.j,  0.+0.j]))

        >>> hx.ket('y')
        HilbertArray(<x|,
        array([ 0.+0.j,  1.+0.j,  0.+0.j]))
        """

        if self.is_dual:
            return self.basis_vec({self: idx})
        else:
            return self.H.basis_vec({self.H: idx})

    # These are implemented as properties rather than setting them in the
    # HilbertSpace constructor in order to avoid self-reference (which would
    # mess up pickle).

    @property
    def bra_ket_set(self):
        return frozenset([self])

    @property
    def bra_set(self):
        if self.is_dual:
            return frozenset([self])
        else:
            return frozenset()

    @property
    def ket_set(self):
        if self.is_dual:
            return frozenset()
        else:
            return frozenset([self])

    @property
    def sorted_bras(self):
        if self.is_dual:
            return [self]
        else:
            return []

    @property
    def sorted_kets(self):
        if self.is_dual:
            return []
        else:
            return [self]

    # Special operators

    def pauliX(self):
        """
        Returns the Pauli X operator.

        This is only available for qubit spaces.

        See also: :func:`X`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.pauliX()
        HilbertArray(|a><a|,
        array([[ 0.+0.j,  1.+0.j],
               [ 1.+0.j,  0.+0.j]]))
        """

        if len(self.indices) != 2:
            raise NotImplementedError("pauliX is only implemented for qubits")
        else:
            return self.O.array([[0, 1], [1, 0]])

    def pauliY(self):
        """
        Returns the Pauli Y operator.

        This is only available for qubit spaces.

        See also: :func:`Y`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.pauliY()
        HilbertArray(|a><a|,
        array([[ 0.+0.j, -0.-1.j],
               [ 0.+1.j,  0.+0.j]]))
        """

        if len(self.indices) != 2:
            raise NotImplementedError("pauliY is only implemented for qubits")
        else:
            j = self.base_field.complex_unit()
            return self.O.array([[0, -j], [j, 0]])

    def pauliZ(self, order=1):
        r"""
        Returns the generalized Pauli Z operator.

        :param order: if given, :math:`Z^\textrm{order}` will be returned.  This is
            only useful for spaces that are larger than qubits.
        :type order: integer; default 1

        See also: :func:`Z`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.pauliZ()
        HilbertArray(|a><a|,
        array([[ 1.+0.j,  0.+0.j],
               [ 0.+0.j, -1.+0.j]]))

        >>> hx = indexed_space('x', ['x', 'y', 'z', 'w'])
        >>> hx.pauliZ()
        HilbertArray(|x><x|,
        array([[ 1.+0.j,  0.+0.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+1.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j, -1.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j,  0.+0.j, -0.-1.j]]))

        >>> hx.pauliZ(2)
        HilbertArray(|x><x|,
        array([[ 1.+0.j,  0.+0.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j, -1.+0.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j,  1.-0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j,  0.+0.j, -1.+0.j]]))
        """

        ret = self.O.array()
        N = len(self.indices)
        for (i, k) in enumerate(self.indices):
            ret[k, k] = self.base_field.fractional_phase(i*order, N)
        return ret

    @property
    def X(self):
        """
        Returns the Pauli X operator.

        This is only available for qubit spaces.

        See also: :func:`pauliX`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.X
        HilbertArray(|a><a|,
        array([[ 0.+0.j,  1.+0.j],
               [ 1.+0.j,  0.+0.j]]))
        """
        return self.pauliX()

    @property
    def Y(self):
        """
        Returns the Pauli Y operator.

        This is only available for qubit spaces.

        See also: :func:`pauliY`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.Y
        HilbertArray(|a><a|,
        array([[ 0.+0.j, -0.-1.j],
               [ 0.+1.j,  0.+0.j]]))
        """
        return self.pauliY()

    @property
    def Z(self):
        """
        Returns the generalized Pauli Z operator.

        See also: :func:`pauliZ`

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.Z
        HilbertArray(|a><a|,
        array([[ 1.+0.j,  0.+0.j],
               [ 0.+0.j, -1.+0.j]]))

        >>> hx = indexed_space('x', ['x', 'y', 'z', 'w'])
        >>> hx.Z
        HilbertArray(|x><x|,
        array([[ 1.+0.j,  0.+0.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+1.j,  0.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j, -1.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+0.j,  0.+0.j, -0.-1.j]]))
        """
        return self.pauliZ()

    def hadamard(self):
        """
        Returns the Hadamard operator.

        This is only available for qubit spaces.

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.hadamard()
        HilbertArray(|a><a|,
        array([[ 0.707107+0.j,  0.707107+0.j],
               [ 0.707107+0.j, -0.707107+0.j]]))
        """

        if len(self.indices) != 2:
            raise NotImplementedError("hadamard is only implemented for qubits")
        else:
            return self.O.array([[1, 1], [1, -1]]) / np.sqrt(2)

    def gateS(self):
        """
        Returns the S-gate operator.

        This is only available for qubit spaces.

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.gateS()
        HilbertArray(|a><a|,
        array([[ 1.+0.j,  0.+0.j],
               [ 0.+0.j,  0.+1.j]]))
        """

        if len(self.indices) != 2:
            raise NotImplementedError("gateS is only implemented for qubits")
        else:
            j = self.base_field.complex_unit()
            return self.O.array([[1, 0], [0, j]])

    def gateT(self):
        """
        Returns the T-gate operator.

        This is only available for qubit spaces.

        >>> from qitensor import *
        >>> ha = qubit('a')
        >>> ha.gateT()
        HilbertArray(|a><a|,
        array([[ 1.000000+0.j      ,  0.000000+0.j      ],
               [ 0.000000+0.j      ,  0.707107+0.707107j]]))
        """

        if len(self.indices) != 2:
            raise NotImplementedError("gateT is only implemented for qubits")
        else:
            ph = self.base_field.fractional_phase(1, 8)
            return self.O.array([[1, 0], [0, ph]])
