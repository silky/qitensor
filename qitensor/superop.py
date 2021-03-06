import numpy as np
import itertools
import random

from qitensor import qudit, direct_sum, NotKetSpaceError, \
    HilbertSpace, HilbertArray, HilbertError, HilbertShapeError, MismatchedSpaceError
from qitensor.space import create_space2

toler = 1e-12

# FIXME - some methods don't have docs
# FIXME - use CP_Map in the map-state duality example
# FIXME - method to relabel input/output/env space
# Possible examples:
#   Space not seen by environment:
#       ha = qudit('a', 5); hb = qudit('b', 8); hc = qudit('c', 3)
#       E = CP_Map((hb*hc*ha.H).random_isometry(), hc)
#         ... or
#       E = CP_Map.random(ha, hb, hc)
#       E.ket().O.trace(hc).span(ha.O)

__all__ = ['Superoperator', 'CP_Map']

def _unreduce_supop_v1(in_space, out_space, m):
    """
    This is the function that handles restoring a pickle.
    """
    return Superoperator(in_space, out_space, m)

class Superoperator(object):
    """
    FIXME: need to write documentation.
    """

    def __init__(self, in_space, out_space, m):
        """
        >>> ha = qudit('a', 3)
        >>> hb = qudit('b', 4)
        >>> E = Superoperator.random(ha, hb)
        >>> X = ha.O.random_array()
        >>> Y = hb.O.random_array()
        >>> # Test the adjoint channel.
        >>> abs( (E(X).H * Y).trace() - (X.H * E.H(Y)).trace() ) < 1e-14
        True
        """

        self._in_space = self._to_ket_space(in_space)
        self._out_space = self._to_ket_space(out_space)
        self._m = np.matrix(m)

        if m.shape != (self.out_space.O.dim(), self.in_space.O.dim()):
            raise HilbertShapeError(m.shape, (self.out_space.O.dim(), self.in_space.O.dim()))

        self._H_S = None

    def __reduce__(self):
        """
        Tells pickle how to store this object.

        >>> import pickle
        >>> from qitensor import qubit, qudit, Superoperator
        >>> ha = qudit('a', 3)
        >>> hb = qubit('b')
        >>> rho = (ha*hb).random_density()

        >>> E = Superoperator.from_function(ha, lambda x: x.T)
        >>> E
        Superoperator( |a><a| to |a><a| )
        >>> F = pickle.loads(pickle.dumps(E))
        >>> F
        Superoperator( |a><a| to |a><a| )
        >>> (E(rho) - F(rho)).norm() < 1e-14
        True
        """

        return _unreduce_supop_v1, (self.in_space, self.out_space, self._m)

    @property
    def in_space(self):
        return self._in_space

    @property
    def out_space(self):
        return self._out_space

    @classmethod
    def _make_environ_spc(cls, espc_def, field, dim):
        if espc_def is None:
            chartab = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            rndstr = ''.join(random.sample(chartab, 6))
            espc_def = 'env_'+rndstr

        if isinstance(espc_def, HilbertSpace):
            if espc_def.dim() < dim:
                raise HilbertError('environment space not big enough: %d vs %d'
                    % (espc_def.dim(), dim))
            return espc_def

        return qudit(espc_def, dim, dtype=field)

    @classmethod
    def _to_ket_space(cls, spc):
        if not spc.bra_set:
            return spc
        if not spc.ket_set:
            return spc.H
        if spc == spc.O:
            return spc.ket_space
        raise NotKetSpaceError('need a bra, ket, or self-adjoint space, not '+str(spc))

    def __str__(self):
        return 'Superoperator( '+str(self.in_space.O)+' to '+str(self.out_space.O)+' )'

    def __repr__(self):
        return str(self)

    def as_matrix(self):
        return self._m

    def __call__(self, rho):
        if not rho.space.bra_ket_set >= self.in_space.O.bra_ket_set:
            raise MismatchedSpaceError("argument space "+repr(rho.space)+
                    " does not contain superop domain "+repr(self.in_space.O))
        (row_space, col_space) = rho._get_row_col_spaces(col_space=self.in_space.O)
        ret_vec = self._m * rho.as_np_matrix(col_space=self.in_space.O)
        if len(row_space):
            out_space = self.out_space.O * np.prod(row_space)
        else:
            out_space = self.out_space.O
        return out_space.array(ret_vec, reshape=True, input_axes=self.out_space.O.axes+row_space)

    def __mul__(self, other):
        """
        >>> from qitensor import qudit, Superoperator
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 3)
        >>> hc = qudit('c', 4)
        >>> hd = qudit('d', 2)
        >>> he = qudit('e', 3)

        >>> rho = (ha*hd).O.random_array()
        >>> E = Superoperator.random(ha, ha)
        >>> E
        Superoperator( |a><a| to |a><a| )

        >>> 2*E
        Superoperator( |a><a| to |a><a| )
        >>> ((2*E)(rho) - 2*E(rho)).norm() < 1e-14
        True

        >>> (-2)*E
        Superoperator( |a><a| to |a><a| )
        >>> (((-2)*E)(rho) - (-2)*E(rho)).norm() < 1e-14
        True

        >>> E1 = Superoperator.random(ha, hb*hc)
        >>> E1
        Superoperator( |a><a| to |b,c><b,c| )
        >>> E2 = Superoperator.random(hc*hd, he)
        >>> E2
        Superoperator( |c,d><c,d| to |e><e| )
        >>> E3 = E2*E1
        >>> E3
        Superoperator( |a,d><a,d| to |b,e><b,e| )
        >>> (E2(E1(rho)) - E3(rho)).norm() < 1e-12 # FIXME - why not 1e-14 precision?
        True
        """

        if isinstance(other, Superoperator):
            common_spc = self.in_space.ket_set & other.out_space.ket_set
            in_spc = (self.in_space.ket_set - common_spc) | other.in_space.ket_set
            in_spc = create_space2(in_spc, frozenset())
            return Superoperator.from_function(in_spc, lambda x: self(other(x)))

        if isinstance(other, HilbertArray):
            return NotImplemented

        # hopefully `other` is a scalar
        return Superoperator(self.in_space, self.out_space, self._m*other)

    def __rmul__(self, other):
        # hopefully `other` is a scalar
        return self * other

    def __add__(self, other):
        """
        >>> from qitensor import qudit, Superoperator
        >>> ha = qudit('a', 4)
        >>> hb = qudit('b', 3)
        >>> E1 = Superoperator.random(ha, hb)
        >>> E2 = Superoperator.random(ha, hb)
        >>> rho = ha.random_density()
        >>> chi = (E1*0.2 + E2*0.8)(rho)
        >>> xi  = E1(rho)*0.2 + E2(rho)*0.8
        >>> (chi - xi).norm() < 1e-14
        True
        """

        if not isinstance(other, Superoperator):
            return NotImplemented

        if self.in_space != other.in_space or self.out_space != other.out_space:
            raise MismatchedSpaceError("spaces do not match: "+
                repr(self.in_space)+" -> "+repr(self.out_space)+" vs. "+
                repr(other.in_space)+" -> "+repr(other.out_space))

        return Superoperator(self.in_space, self.out_space, self._m + other._m)

    def __neg__(self):
        """
        >>> from qitensor import qudit, Superoperator
        >>> ha = qudit('a', 4)
        >>> hb = qudit('b', 3)
        >>> E = Superoperator.random(ha, hb)
        >>> rho = ha.random_density()
        >>> ((-E)(rho) + E(rho)).norm() < 1e-14
        True
        """

        return (-1)*self

    def __sub__(self, other):
        """
        >>> from qitensor import qudit, Superoperator
        >>> ha = qudit('a', 4)
        >>> hb = qudit('b', 3)
        >>> E1 = Superoperator.random(ha, hb)
        >>> E2 = Superoperator.random(ha, hb)
        >>> rho = ha.random_density()
        >>> chi = (E1 - E2)(rho)
        >>> xi  = E1(rho) - E2(rho)
        >>> (chi - xi).norm() < 1e-14
        True
        """

        return self + (-other)

    @property
    def H(self):
        """The adjoint channel."""
        if self._H_S is None:
            da = self.in_space.dim()
            db = self.out_space.dim()
            MH = self.as_matrix().A.conj().reshape(db,db,da,da).transpose(2,3,0,1). \
                    reshape(da*da, db*db)
            self._H_S = Superoperator(self.out_space, self.in_space, MH)
        return self._H_S

    @classmethod
    def from_function(cls, in_space, f):
        """
        >>> from qitensor import qudit, Superoperator
        >>> ha = qudit('a', 3)
        >>> hb = qudit('b', 4)
        >>> rho = (ha*hb).random_density()

        >>> ET = Superoperator.from_function(ha, lambda x: x.T)
        >>> ET
        Superoperator( |a><a| to |a><a| )
        >>> (ET(rho) - rho.transpose(ha)).norm() < 1e-14
        True

        >>> hc = qudit('c', 5)
        >>> L = (hc*ha.H).random_array()
        >>> R = (ha*hc.H).random_array()
        >>> N = Superoperator.from_function(ha, lambda x: L*x*R)
        >>> N
        Superoperator( |a><a| to |c><c| )
        >>> (N(rho) - L*rho*R).norm() < 1e-14
        True

        >>> Superoperator.from_function(ha, lambda x: x.H)
        Traceback (most recent call last):
            ...
        ValueError: function was not linear
        """

        in_space = cls._to_ket_space(in_space)
        out_space = f(in_space.eye()).space
        if out_space != out_space.H:
            raise MismatchedSpaceError("out space was not symmetric: "+repr(out_space))
        out_space = out_space.ket_space()

        m = np.zeros((out_space.dim()**2, in_space.dim()**2), in_space.base_field.dtype)
        for (i, x) in enumerate(in_space.O.index_iter()):
            m[:, i] = f(in_space.O.basis_vec(x)).nparray.flatten()

        E = Superoperator(in_space, out_space, m)

        rho = in_space.random_density()
        if (E(rho) - f(rho)).norm() > toler:
            raise ValueError('function was not linear')

        return E

    @classmethod
    def random(cls, spc_in, spc_out):
        in_space = cls._to_ket_space(spc_in)
        out_space = cls._to_ket_space(spc_out)
        m = spc_in.base_field.random_array((out_space.O.dim(), in_space.O.dim()))
        return Superoperator(in_space, out_space, m)

    @classmethod
    def transposer(cls, spc):
        """
        >>> from qitensor import qubit, qudit, Superoperator
        >>> ha = qudit('a', 3)
        >>> hb = qubit('b')
        >>> rho = (ha*hb).random_density()

        >>> T = Superoperator.transposer(ha)
        >>> T
        Superoperator( |a><a| to |a><a| )
        >>> (T(rho) - rho.transpose(ha)).norm() < 1e-14
        True
        """

        return cls.from_function(spc, lambda x: x.T)

    def upgrade_to_cp_map(self, espc_def=None):
        return CP_Map.from_matrix(self._m, self.in_space, self.out_space, espc_def=espc_def)

    def upgrade_to_cptp_map(self, espc_def=None):
        ret = self.upgrade_to_cp_map()
        ret.assert_cptp()
        return ret

def _unreduce_cpmap_v1(in_space, out_space, env_space, J):
    """
    This is the function that handles restoring a pickle.
    """
    return CP_Map(J, env_space)

class CP_Map(Superoperator):
    """
    FIXME: need to write documentation.
    """

    def __init__(self, J, env_space):
        """
        >>> ha = qudit('a', 3)
        >>> hb = qudit('b', 4)
        >>> hd = qudit('d', 3)
        >>> rho = (ha*hd).random_density()
        >>> E = CP_Map.random(ha, hb)
        >>> # Test the channel via its isometry.
        >>> ((E.J * rho * E.J.H).trace(E.env_space) - E(rho)).norm() < 1e-14
        True
        >>> # Test complementary channel.
        >>> ((E.J * rho * E.J.H).trace(hb) - E.C(rho)).norm() < 1e-14
        True

        >>> X = ha.O.random_array()
        >>> Y = hb.O.random_array()
        >>> # Test the adjoint channel.
        >>> abs( (E(X).H * Y).trace() - (X.H * E.H(Y)).trace() ) < 1e-14
        True
        """

        env_space = self._to_ket_space(env_space)
        in_space = J.space.bra_space().H
        if not J.space.ket_set >= env_space.ket_set:
            raise MismatchedSpaceError("J output does not contain env_space: "+repr(J.ket_space)+
                    " vs. "+repr(env_space))
        out_space = J.space.ket_set - env_space.ket_set
        out_space = create_space2(out_space, frozenset())

        assert J.space == out_space * env_space * in_space.H

        da = in_space.dim()
        db = out_space.dim()
        t = np.zeros((db, da, db, da), dtype=in_space.base_field.dtype)
        for j in env_space.index_iter():
            op = J[{ env_space: j }].as_np_matrix(row_space=in_space.H)
            t += np.tensordot(op, op.conj(), axes=([],[]))
        t = t.transpose([0,2,1,3])
        t = t.reshape(db**2, da**2)
        t = np.matrix(t)

        super(CP_Map, self).__init__(in_space, out_space, t)

        self._J = J
        self._env_space = env_space
        self._C = None
        self._H_CP = None

    def __reduce__(self):
        """
        Tells pickle how to store this object.

        >>> import pickle
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> rho = ha.O.random_array()
        >>> E = CP_Map.random(ha, ha)
        >>> F = pickle.loads(pickle.dumps(E))
        >>> F
        CP_Map( |a><a| to |a><a| )
        >>> (E(rho) - F(rho)).norm() < 1e-14
        True
        """

        return _unreduce_cpmap_v1, (self.in_space, self.out_space, self.env_space, self.J)

    @property
    def env_space(self):
        return self._env_space

    @property
    def J(self):
        """The channel isometry."""
        return self._J

    @property
    def C(self):
        """The complimentary channel."""
        if self._C is None:
            self._C = CP_Map(self.J, self.out_space)
        return self._C

    @property
    def H(self):
        """The adjoint channel."""
        if self._H_CP is None:
            JH = self.J.H.relabel({ self.env_space.H: self.env_space })
            self._H_CP = CP_Map(JH, self.env_space)
        return self._H_CP

    def ket(self):
        """
        Returns the channel ket.

        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 2)
        >>> E = CP_Map.random(ha, hb, 'c')
        >>> E.J.space
        |b,c><a|
        >>> E.ket().space
        |a,b,c>
        >>> F = CP_Map.random(ha, ha, 'c')
        >>> F.ket()
        Traceback (most recent call last):
            ...
        HilbertError: 'channel ket can only be made if input space is different from output and environment spaces'
        """

        if not self.in_space.ket_set.isdisjoint(self.J.space.ket_set):
            raise HilbertError('channel ket can only be made if input space is different '+
                'from output and environment spaces')
        return self.J.transpose(self.in_space)

    def is_cptp(self):
        return (self.J.H*self.J - self.in_space.eye()).norm() < toler

    def assert_cptp(self):
        if not self.is_cptp():
            raise ValueError('channel is not trace preserving')

    def krauses(self):
        """
        Returns the channel ket.

        >>> import numpy
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 2)
        >>> E = CP_Map.random(ha, hb)
        >>> len(E.krauses())
        4
        >>> E.krauses()[0].space
        |b><a|
        >>> # Test closure condition.
        >>> ( numpy.sum([ x.H * x for x in E.krauses() ]) - ha.eye() ).norm() < 1e-14
        True
        """

        return [ self.J[{ self.env_space: x }] for x in self.env_space.indices ]

    def __str__(self):
        return 'CP_Map( '+str(self.in_space.O)+' to '+str(self.out_space.O)+' )'

    def __repr__(self):
        return str(self)

    def __mul__(self, other):
        """
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 3)
        >>> hc = qudit('c', 2)
        >>> hd = qudit('d', 2)
        >>> he = qudit('e', 3)

        >>> rho = (ha*hd).O.random_array()
        >>> E = CP_Map.random(ha, ha)
        >>> E
        CP_Map( |a><a| to |a><a| )

        >>> 2*E
        CP_Map( |a><a| to |a><a| )
        >>> ((2*E)(rho) - 2*E(rho)).norm() < 1e-14
        True

        >>> (-2)*E
        Superoperator( |a><a| to |a><a| )
        >>> (((-2)*E)(rho) - (-2)*E(rho)).norm() < 1e-14
        True

        >>> E*E
        CP_Map( |a><a| to |a><a| )
        >>> ((E*E)(rho) - E(E(rho))).norm() < 1e-14
        True

        >>> E1 = CP_Map.random(ha, hb*hc, 'env1')
        >>> E1
        CP_Map( |a><a| to |b,c><b,c| )
        >>> E2 = CP_Map.random(hc*hd, he, 'env2')
        >>> E2
        CP_Map( |c,d><c,d| to |e><e| )
        >>> E3 = E2*E1
        >>> E3
        CP_Map( |a,d><a,d| to |b,e><b,e| )
        >>> E3.env_space
        |env1,env2>
        >>> (E2(E1(rho)) - E3(rho)).norm() < 1e-14
        True
        """

        if isinstance(other, CP_Map):
            common_spc = self.in_space.ket_set & other.out_space.ket_set
            in_spc  = (self.in_space.ket_set - common_spc) | other.in_space.ket_set
            out_spc = self.out_space.ket_set | (other.out_space.ket_set - common_spc)
            in_spc  = create_space2(in_spc , frozenset())
            out_spc = create_space2(out_spc, frozenset())

            # If the multiplicands have disjoint environments, then the product will use the
            # product environment.  Otherwise, a new environment is created.
            if self.env_space.ket_set.isdisjoint(other.env_space.ket_set):
                env = self.env_space * other.env_space
                return CP_Map(self.J*other.J, env)
            else:
                return super(CP_Map, self).__mul__(other).upgrade_to_cp_map()

        if isinstance(other, Superoperator):
            return super(CP_Map, self).__mul__(other)

        if isinstance(other, HilbertArray):
            return NotImplemented

        # hopefully `other` is a scalar
        if other < 0:
            return super(CP_Map, self).__mul__(other)
        else:
            s = self.in_space.base_field.sqrt(other)
            return CP_Map(self.J*s, self.env_space)

    def __rmul__(self, other):
        # hopefully `other` is a scalar
        return self * other

    def __add__(self, other):
        ret = super(CP_Map, self).__add__(other)
        if isinstance(other, CP_Map):
            # FIXME - reuse env_space if possible
            return ret.upgrade_to_cp_map()
        else:
            return ret

    def add2(self, other):
        """
        Adds two CP maps.  The returned map has the same action as E1+E2, but the environment
        is the direct sum of the component environments.

        >>> import numpy.linalg as linalg
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 3)
        >>> E1 = CP_Map.random(ha, hb, 'hc1')
        >>> E2 = CP_Map.random(ha, hb, 'hc2')
        >>> X = E1 + E2
        >>> Y = E1.add2(E2)
        >>> linalg.norm(X.as_matrix() - Y.as_matrix()) < 1e-14
        True
        >>> (E1.env_space, E2.env_space, Y.env_space)
        (|hc1>, |hc2>, |hc1+hc2>)
        """

        if not isinstance(other, CP_Map):
            raise ValueError('other was not a CP_Map')

        if self.in_space != other.in_space or self.out_space != other.out_space:
            raise MismatchedSpaceError("spaces do not match: "+
                repr(self.in_space)+" -> "+repr(self.out_space)+" vs. "+
                repr(other.in_space)+" -> "+repr(other.out_space))

        ret_hc = direct_sum((self.env_space, other.env_space))
        ret_J = ret_hc.P[0]*self.J + ret_hc.P[1]*other.J
        return CP_Map(ret_J, ret_hc)

    def coherent_information(self, rho):
        """
        Compute S(B)-S(C) after passing the given state through the channel.
        """

        if rho.space != rho.H.space:
            raise HilbertError("rho did not have equal bra and ket spaces: "+str(rho.space))
        if np.abs(rho.trace() - 1) > toler:
            raise ValueError("rho didn't have trace=1")

        return self(rho).tracekeep(self.out_space).entropy() - self.C(rho).tracekeep(self.env_space).entropy()

    def private_information(self, ensemble):
        """
        Compute I(X;B) - I(X;C) where X is a classical ancillary system that records which
        state of the ensemble was passed through the channel.
        """

        ensemble = list(ensemble)
        dx = len(ensemble)
        hx = self._make_environ_spc(None, self.in_space.base_field, dx)
        rho = np.sum([ hx.ket(i).O * rho_i for (i, rho_i) in enumerate(ensemble) ])

        if rho.space != rho.H.space:
            raise HilbertError("ensemble was not on a Hermitian space: "+rho.space)
        if np.abs(rho.trace() - 1) > toler:
            raise ValueError("your ensemble didn't have trace=1")

        return self(rho).mutual_info(hx, self.out_space) - self.C(rho).mutual_info(hx, self.env_space)

    @classmethod
    def from_function(cls, in_space, f, espc_def=None):
        """
        >>> from qitensor import qubit, qudit, CP_Map
        >>> ha = qudit('a', 3)
        >>> hb = qubit('b')
        >>> rho = (ha*hb).random_density()

        >>> CP_Map.from_function(ha, lambda x: x.T)
        Traceback (most recent call last):
            ...
        ValueError: matrix didn't correspond to a completely positive superoperator (min eig=-1.0)

        >>> U = ha.random_unitary()
        >>> EU = CP_Map.from_function(ha, lambda x: U*x*U.H)
        >>> EU
        CP_Map( |a><a| to |a><a| )
        >>> (EU(rho) - U*rho*U.H).norm() < 1e-14
        True
        """

        E = Superoperator.from_function(in_space, f)
        E = E.upgrade_to_cp_map(espc_def)
        return E

    @classmethod
    def from_matrix(cls, m, spc_in, spc_out, espc_def=None, compact_environ_tol=1e-12):
        """
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 2)
        >>> hb = qudit('b', 3)
        >>> hx = qudit('x', 5)
        >>> E1 = CP_Map.random(ha*hb, hx)
        >>> E2 = CP_Map.random(hx, ha*hb)
        >>> m = E2.as_matrix() * E1.as_matrix()
        >>> E3 = CP_Map.from_matrix(m, ha*hb, ha*hb)
        >>> rho = (ha*hb).random_density()
        >>> (E2(E1(rho)) - E3(rho)).norm() < 1e-14
        True
        """

        in_space = cls._to_ket_space(spc_in)
        out_space = cls._to_ket_space(spc_out)
        da = in_space.dim()
        db = out_space.dim()
        t = np.array(m)

        if t.shape != (db*db, da*da):
            raise HilbertShapeError("matrix wrong size for given spaces: "+
                    repr(t.shape)+" vs. "+repr((db*db, da*da)))

        t = t.reshape(db, db, da, da)
        t = t.transpose([0, 2, 1, 3])
        t = t.reshape(db*da, db*da)

        field = in_space.base_field

        if field.mat_norm(np.transpose(np.conj(t)) - t, 2) > toler:
            raise ValueError("matrix didn't correspond to a completely positive "+
                "superoperator (cross operator not self-adjoint)")

        (ew, ev) = field.mat_eig(t, hermit=True)

        if np.min(ew) < -toler:
            raise ValueError("matrix didn't correspond to a completely positive "+
                "superoperator (min eig="+str(np.min(ew))+")")
        ew = np.where(ew < 0, 0, ew)

        if compact_environ_tol:
            nonzero = np.nonzero(ew > compact_environ_tol)[0]
            dc = len(nonzero)
        else:
            dc = da*db
            nonzero = list(range(dc))

        env_space = cls._make_environ_spc(espc_def, in_space.base_field, dc)

        J = (out_space * env_space * in_space.H).array()

        for (i, j) in enumerate(nonzero):
            J[{ env_space: i }] = (out_space * in_space.H).array(ev[:,j] * field.sqrt(ew[j]), reshape=True)

        return CP_Map(J, env_space)

    @classmethod
    def from_kraus(cls, ops, espc_def=None):
        ops = list(ops)
        op_spc = ops[0].space
        dc = len(ops)
        env_space = cls._make_environ_spc(espc_def, op_spc.base_field, dc)
        J = (op_spc * env_space).array()
        for (i, op) in enumerate(ops):
            J[{ env_space: i }] = op

        return CP_Map(J, env_space)

    @classmethod
    def random(cls, spc_in, spc_out, espc_def=None):
        """
        Return a random CPTP map.  The channel's isometry is distributed uniformly over the
        Haar measure.

        :param espc_def: a HilbertSpace for the environment, or a label for that space if a
            string is provided, or the dimension of the environment if an integer is provided.
            If not specified, the environment will have full dimension.
        """

        in_space = cls._to_ket_space(spc_in)
        out_space = cls._to_ket_space(spc_out)
        if isinstance(espc_def, HilbertSpace):
            dc = espc_def.dim()
        elif isinstance(espc_def, int):
            dc = espc_def
            espc_def = None
        else:
            dc = in_space.dim() * out_space.dim()
        env_space = cls._make_environ_spc(espc_def, in_space.base_field, dc)
        J = (out_space*env_space*in_space.H).random_isometry()
        return CP_Map(J, env_space)

    @classmethod
    def unitary(cls, U, espc_def=None):
        """
        >>> from qitensor import qubit, CP_Map
        >>> ha = qubit('a')
        >>> hb = qubit('b')
        >>> U = ha.random_unitary()
        >>> rho = (ha*hb).random_density()
        >>> E = CP_Map.unitary(U)
        >>> (E(rho) - U*rho*U.H).norm() < 1e-14
        True
        """

        env_space = cls._make_environ_spc(espc_def, U.space.base_field, 1)
        J = U * env_space.ket(0)
        return CP_Map(J, env_space)

    @classmethod
    def identity(cls, spc, espc_def=None):
        """
        >>> from qitensor import qubit, CP_Map
        >>> ha = qubit('a')
        >>> hb = qubit('b')
        >>> rho = (ha*hb).random_density()
        >>> E = CP_Map.identity(ha)
        >>> (E(rho) - rho).norm() < 1e-14
        True
        """

        return cls.unitary(spc.eye(), espc_def)

    @classmethod
    def totally_noisy(cls, spc, espc_def=None):
        """
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 5)
        >>> rho = ha.random_density()
        >>> E = CP_Map.totally_noisy(ha)
        >>> (E(rho) - ha.fully_mixed()).norm() < 1e-14
        True
        """

        in_space = cls._to_ket_space(spc)
        d = in_space.dim()
        d2 = d*d
        env_space = cls._make_environ_spc(espc_def, in_space.base_field, d2)
        J = (in_space.O*env_space).array()
        for (i, (j, k)) in enumerate(itertools.product(in_space.index_iter(), repeat=2)):
            J[{ in_space.H: j, in_space: k, env_space: i }] = 1
        J /= in_space.base_field.sqrt(d)
        return CP_Map(J, env_space)

    @classmethod
    def noisy(cls, spc, p, espc_def=None):
        """
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 5)
        >>> rho = ha.random_density()
        >>> E = CP_Map.noisy(ha, 0.2)
        >>> (E(rho) - 0.8*rho - 0.2*ha.fully_mixed()).norm() < 1e-14
        True
        """

        if not (0 <= p <= 1):
            raise HilbertError("p must be in [0,1], but it was "+repr(p))

        E0 = cls.totally_noisy(spc)
        E1 = cls.identity(spc)
        return p*E0 + (1-p)*E1

    @classmethod
    def decohere(cls, spc, espc_def=None):
        """
        >>> from qitensor import qudit, CP_Map
        >>> ha = qudit('a', 5)
        >>> rho = ha.random_density()
        >>> E = CP_Map.decohere(ha)
        >>> (E(rho) - ha.diag(rho.diag(as_np=True))).norm() < 1e-14
        True
        """

        in_space = cls._to_ket_space(spc)
        d = in_space.dim()
        env_space = cls._make_environ_spc(espc_def, in_space.base_field, d)
        J = (in_space.O*env_space).array()
        for (i, a) in enumerate(in_space.index_iter()):
            J[{ in_space.H: a, in_space: a, env_space: i }] = 1
        return CP_Map(J, env_space)

    @classmethod
    def erasure(cls, spc, p, bspc_def=None, espc_def=None):
        """
        Create a channel that has probability p of erasing the input, and 1-p of perfectly
        transmitting the input.  The output space has dimension one greater than the input
        space, and the receiver is notified of erasure via the extra computational basis state.
        If p=0.5 then the channel is symmetric.
        """

        if p < 0 or p > 1:
            raise ValueError("p must be in [0, 1]")

        in_space = cls._to_ket_space(spc)
        d = in_space.dim()
        out_space = cls._make_environ_spc(bspc_def, in_space.base_field, d+1)
        env_space = cls._make_environ_spc(espc_def, in_space.base_field, d+1)
        J = (out_space * env_space * in_space.H).array()
        J += np.sqrt(  p) * out_space.ket(d) * (env_space * in_space.H).array(np.eye(d+1, d), reshape=True)
        J += np.sqrt(1-p) * env_space.ket(d) * (out_space * in_space.H).array(np.eye(d+1, d), reshape=True)
        return CP_Map(J, env_space)
