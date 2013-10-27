# Noncommutative graphs as defined by Duan, Severini, Winter in arXiv:1002.2514.

import numpy as np
import numpy.linalg as linalg
import itertools
import cvxopt.base
import cvxopt.solvers

from qitensor.subspace import TensorSubspace

# This is the only thing that is exported.
__all__ = ['NoncommutativeGraph']

### Some helper functions for cvxopt ###

def mat_cplx_to_real(cmat):
    rmat = np.zeros((2, cmat.shape[0], 2, cmat.shape[1]))
    rmat[0, :, 0, :] = cmat.real
    rmat[1, :, 1, :] = cmat.real
    rmat[0, :, 1, :] = -cmat.imag
    rmat[1, :, 0, :] = cmat.imag
    return rmat.reshape(cmat.shape[0]*2, cmat.shape[1]*2)

# This could help for extracting the dual solution for the solver.  But I haven't yet figured
# out how to interpret the things that cvxopt returns.
#ret=NoncommutativeGraph(S).lovasz_theta(long_return=True)
#ss=mat_real_to_cplx(np.array(ret['sdp_stats']['ss'][1]))
#zs=mat_real_to_cplx(np.array(ret['sdp_stats']['zs'][1]))
def mat_real_to_cplx(rmat):
    w = rmat.shape[0]/2
    h = rmat.shape[1]/2
    return rmat[:w,:h] + 1j*rmat[w:,:h]

def make_F_real(Fx_list, F0_list):
    '''
    Convert F0, Fx arrays to real if needed, by considering C as a vector space
    over R.  This is needed because cvxopt cannot handle complex inputs.
    '''

    F0_list_real = []
    Fx_list_real = []
    for (F0, Fx) in zip(F0_list, Fx_list):
        if F0.dtype.kind == 'c' or Fx.dtype.kind == 'c':
            F0_list_real.append(mat_cplx_to_real(F0))

            mr = np.zeros((Fx.shape[0]*2, Fx.shape[1]*2, Fx.shape[2]))
            for i in range(Fx.shape[2]):
                mr[:, :, i] = mat_cplx_to_real(Fx[:, :, i])
            Fx_list_real.append(mr)
        else:
            F0_list_real.append(F0)
            Fx_list_real.append(Fx)

    assert len(F0_list_real) == len(F0_list)
    assert len(Fx_list_real) == len(Fx_list)
    return (Fx_list_real, F0_list_real)

def call_sdp(c, Fx_list, F0_list):
    '''
    Solve the SDP which minimizes $c^T x$ under the constraint
    $\sum_i Fx_i x_i - F0 \ge 0$ for all (Fx, F0) in (Fx_list, F0_list).
    '''

    # Alternatively, the SDPA library can be used, but this requires
    # interfacing to C libraries.
    #xvec = sdpa.run_sdpa(c, Fx_list, F0_list).

    for (k, (F0, Fx)) in enumerate(zip(F0_list, Fx_list)):
        assert linalg.norm(F0 - F0.conj().T) < 1e-10
        for i in range(Fx.shape[2]):
            assert linalg.norm(Fx[:,:,i] - Fx[:,:,i].conj().T) < 1e-10

    # Note: Fx and F0 must be negated when passed to cvxopt.sdp.
    (Fx_list, F0_list) = make_F_real(Fx_list, F0_list)
    Gs = [cvxopt.base.matrix(-Fx.reshape(Fx.shape[0]**2, Fx.shape[2])) for Fx in Fx_list]
    hs = [cvxopt.base.matrix(-F0) for F0 in F0_list]

    sol = cvxopt.solvers.sdp(cvxopt.base.matrix(c), Gs=Gs, hs=hs)
    xvec = np.array(sol['x']).flatten()

    for (G, h) in zip(Gs, hs):
        G = np.array(G)
        h = np.array(h)
        M = np.dot(G, xvec).reshape(h.shape)
        assert linalg.eigvalsh(h-M)[0] > -1e-7

    return (xvec, sol)

### The main code ######################

class NoncommutativeGraph(object):
    """Non-commutative graphs as described in arXiv:1002.2514."""

    def __init__(self, S):
        """
        Create a non-commutative graph from provided TensorSubspace.
        """

        assert S.is_hermitian()

        self.S = S

        # Make it a space over rank-2 tensors.
        self.S_flat = S._op_flatten()
        assert self.S_flat._col_shp[0] == self.S_flat._col_shp[1]
        self.n = self.S_flat._col_shp[0]

        self.S_basis  = np.array(self.S_flat.basis()) \
                if self.S_flat.dim() else np.zeros((0, self.n, self.n), dtype=complex)
        self.Sp_basis = np.array(self.S_flat.perp().basis()) \
                if self.S_flat.perp().dim() else np.zeros((0, self.n, self.n), dtype=complex)
        assert len(self.S_basis.shape) == 3
        assert len(self.Sp_basis.shape) == 3

        assert np.eye(self.n) in self.S_flat

    @classmethod
    def from_adjmat(cls, adj_mat):
        """
        Create a non-commutative graph from the adjacency matrix of a classical graph.

        The given adjacency matrix must be symmetric.

        >>> from noncommgraph import NoncommutativeGraph
        >>> import numpy
        >>> # 5-cycle graph
        >>> adj_mat = np.array([
        ...     [1, 1, 0, 0, 1],
        ...     [1, 1, 1, 0, 0],
        ...     [0, 1, 1, 1, 0],
        ...     [0, 0, 1, 1, 1],
        ...     [1, 0, 0, 1, 1]
        ... ])
        >>> G = NoncommutativeGraph.from_adjmat(adj_mat)
        >>> theta = G.lovasz_theta()
        >>> abs(theta - numpy.sqrt(5)) < 1e-8
        True
        """

        assert len(adj_mat.shape) == 2
        assert adj_mat.shape[0] == adj_mat.shape[1]
        assert np.all(adj_mat == adj_mat.transpose())
        n = adj_mat.shape[0]
        basis = []

        # copy and cast to numpy
        adj_mat = np.array(adj_mat)

        for (i, j) in np.transpose(adj_mat.nonzero()):
            m = np.zeros((n, n), dtype=complex)
            m[i, j] = 1
            basis.append(m)

        return cls(TensorSubspace.from_span(basis))

    @classmethod
    def from_sagegraph(cls, G):
        """
        Create a non-commutative graph from a Sage Graph.

        Actually, all that is required is that the input G supports an
        adjacency_matrix method.
        """

        return cls.from_adjmat(G.adjacency_matrix())

    @classmethod
    def pentagon(cls):
        """
        Create the 5-cycle graph.  Useful for testing.
        """

        # Adjacency matric for the 5-cycle graph.
        adj_mat = np.array([
            [1, 1, 0, 0, 1],
            [1, 1, 1, 0, 0],
            [0, 1, 1, 1, 0],
            [0, 0, 1, 1, 1],
            [1, 0, 0, 1, 1]
        ])
        G = cls.from_adjmat(adj_mat)
        return G

    def _get_Y_basis(self):
        """
        Compute a basis for the allowed Y operators for Theorem 9 of
        arXiv:1002.2514.  These are the operators which are Hermitian and are
        in S*L(A').  Note that this basis is intended to map real vectors to
        complex Y operators.
        """

        (nS, n, _n) = self.S_basis.shape
        assert n == _n

        Sb = self.S_flat.hermitian_basis()
        Lb = TensorSubspace.full((n, n)).hermitian_basis()

        baz = np.zeros((nS*n*n, n, n, n, n), dtype=complex)
        i = 0
        for x in Sb:
            for y in Lb:
                baz[i] = np.tensordot(x, y, axes=([],[])).transpose((0, 2, 1, 3))
                i += 1
        assert i == baz.shape[0]

        ret = baz.transpose((1, 2, 3, 4, 0))

        # [ |a>, |a'>, <a|, <a'| ; idx ]
        return ret

    def test_get_Y_basis_doubly_hermit(self):
        Yb = self._get_Y_basis()
        Hb = self._basis_doubly_hermit(TensorSubspace.full((n,n)))
        A = TensorSubspace.from_span([ mat_cplx_to_real(Yb[:,:,:,:,i].reshape((n*n, n*n))) for i in range(Yb.shape[4]) ])
        B = TensorSubspace.from_span([ mat_cplx_to_real(Hb[:,:,:,:,i].reshape((n*n, n*n))) for i in range(Hb.shape[4]) ])
        C = A & B
        print A,B,C
        out = np.array([ mat_real_to_cplx(x).reshape((n,n,n,n)) for x in C ])
        for (i,c) in enumerate(np.rollaxis(Hb, -1)):
            x = c.reshape((n*n, n*n))
            y = mat_real_to_cplx(mat_cplx_to_real(x))
            assert linalg.norm(x - x.conj().T) < 1e-10
            assert np.allclose(x, y)
        for (i,c) in enumerate(B):
            x = mat_real_to_cplx(c)
            assert linalg.norm(x - x.conj().T) < 1e-10
        for (i,c) in enumerate(C):
            x = mat_real_to_cplx(c)
            assert linalg.norm(x - x.conj().T) < 1e-10
        a = TensorSubspace.from_span([ mat_cplx_to_real(x.reshape(n*n,n*n)) for x in \
                np.rollaxis(self._basis_doubly_hermit(self.S_flat), -1) ])
        b = TensorSubspace.from_span([ mat_cplx_to_real(x.reshape(n*n,n*n)) for x in out ])
        print a
        print b
        print a.equiv(b)
        assert a.equiv(b)

    def test_doubly_hermitian_basis(self):
        n = self.n

        def perms(i,j,k,l):
            return [(i,j,k,l), (j,i,l,k), (l,k,j,i), (k,l,i,j)]

        inds = set()
        for (i,j,k,l) in itertools.product(range(n), repeat=4):
            p = perms(i,j,k,l)
            if not np.any([ x in inds for x in p ]):
                inds.add((i,j,k,l))

        ops = []
        for (i,j,k,l) in inds:
            a = np.zeros((n,n,n,n), dtype=complex)
            a[i,j,k,l] = 1
            a += a.transpose((1,0,3,2))
            a += a.transpose((2,3,0,1))
            ops.append(a)

            a = np.zeros((n,n,n,n), dtype=complex)
            a[i,j,k,l] = 1j
            a += a.transpose((1,0,3,2)).conj()
            a += a.transpose((2,3,0,1)).conj()
            if np.sum(np.abs(a)) > 1e-6:
                ops.append(a)

        full = TensorSubspace.full((n,n))
        a = TensorSubspace.from_span([ mat_cplx_to_real(x.reshape(n*n,n*n)) for x in \
                np.rollaxis(self._basis_doubly_hermit(full), -1) ])
        b = TensorSubspace.from_span([ mat_cplx_to_real(x.reshape(n*n,n*n)) for x in ops ])
        print a
        print b
        print a.equiv(b)
        assert a.equiv(b)

    def _basis_doubly_hermit(self, spc):
        """
        Returns a basis of elements of spc \ot spc that are Hermitian and also have Hermitian
        images under R().
        """

        Sb = spc.hermitian_basis()
        out = []
        for (i, x) in enumerate(Sb):
            out.append( np.tensordot(x, x.conj(), axes=([],[])).transpose((0, 2, 1, 3)) )
            for (j, y) in enumerate(Sb):
                if j >= i:
                    continue;
                xy = np.tensordot(x, y.conj(), axes=([],[])).transpose((0, 2, 1, 3))
                yx = np.tensordot(y, x.conj(), axes=([],[])).transpose((0, 2, 1, 3))
                out.append(xy+yx)

        ret = np.array(out).transpose((1, 2, 3, 4, 0))

        # [ |a>, |a'>, <a|, <a'| ; idx ]
        return ret

    def lovasz_theta(self, long_return=False):
        """
        Compute the non-commutative generalization of the Lovasz function,
        using Theorem 9 of arXiv:1002.2514.

        If the long_return option is True, then some extra status and internal
        quantities are returned (such as the optimal Y operator).
        """

        (nS, n, _n) = self.S_basis.shape
        assert n == _n

        Y_basis = self._get_Y_basis()
        # x = [t, Y.A:Si * Y.A':i * Y.A':j]
        xvec_len = 1 + Y_basis.shape[4]
        x_to_Y = np.concatenate((
                np.zeros((n,n,n,n, 1)),
                Y_basis
            ), axis=4)
        assert x_to_Y.shape[4] == xvec_len

        phi_phi = np.zeros((n,n, n,n), dtype=complex)
        for (i, j) in itertools.product(range(n), repeat=2):
            phi_phi[i, i, j, j] = 1
        phi_phi = phi_phi.reshape(n**2, n**2)

        # Cost vector.
        # x = [t, Y.A:Si * Y.A':i * Y.A':j]
        c = np.zeros(xvec_len)
        c[0] = 1

        # tI - tr_A{Y} >= 0
        Fx_1 = -np.trace(x_to_Y, axis1=0, axis2=2)
        for i in xrange(n):
            Fx_1[i, i, 0] = 1

        F0_1 = np.zeros((n, n))

        # Y - |phi><phi| >= 0
        Fx_2 = x_to_Y.reshape(n**2, n**2, xvec_len)
        F0_2 = phi_phi

        (xvec, sdp_stats) = call_sdp(c, (Fx_1, Fx_2), (F0_1, F0_2))
        if sdp_stats['status'] != 'optimal':
            raise ArithmeticError(sdp_stats['status'])

        t = xvec[0]
        Y = np.dot(x_to_Y, xvec)

        # some sanity checks to make sure the output makes sense
        verify_tol=1e-7
        if verify_tol:
            err = linalg.eigvalsh(np.dot(Fx_1, xvec).reshape(n, n)   - F0_1)[0] > -verify_tol
            if err < -verify_tol: print "WARNING: F1 err =", err
            err = linalg.eigvalsh(np.dot(Fx_2, xvec).reshape(n**2, n**2) - F0_2)[0]
            if err < -verify_tol: print "WARNING: F2 err =", err
            err = linalg.eigvalsh(Y.reshape(n**2, n**2) - phi_phi)[0]
            if err < -verify_tol: print "WARNING: phi_phi err =", err
            maxeig = linalg.eigvalsh(np.trace(Y, axis1=0, axis2=2))[-1].real
            err = abs(np.dot(c, xvec) - maxeig)
            if err > verify_tol: print "WARNING: t err =", err

            # make sure it is in S*L(A')
            for mat in self.Sp_basis:
                dp = np.tensordot(Y, mat.conjugate(), axes=[[0, 2], [0, 1]])
                err = linalg.norm(dp)
                if err > 1e-13: print "err:", err
                assert err < 1e-13

        if long_return:
            ret = {}
            for key in ['n', 'x_to_Y', 'Fx_1', 'Fx_2', 'F0_1', 'F0_2', 'phi_phi', 'c', 't', 'Y', 'xvec', 'sdp_stats']:
                ret[key] = locals()[key]
            return ret
        else:
            return t

    def schrijver(self, ppt, long_return=False):
        """
        My non-commutative generalization of Schrijver's number.

        min t s.t.
            tI - Tr_A (Y-Z) \succeq 0
            Y \in S \ot \mathcal{L}
            Y-Z (-Z2) \succeq \Phi
            R(Z) \succeq 0
            optional: R(Z2) \in PPT
        """

        (nS, n, _n) = self.S_basis.shape
        assert n == _n

        Y_basis = self._get_Y_basis()
        Yb_len = Y_basis.shape[4]
        Z_basis = self._basis_doubly_hermit(TensorSubspace.full((n,n)))
        Zb_len = Z_basis.shape[4]

        # x = [t, Y.A:Si * Y.A':i * Y.A':j, Z]
        xvec_len = 1 + Yb_len + Zb_len
        if ppt:
            xvec_len += Zb_len

        idx = 1
        x_to_Y = np.zeros((n,n,n,n,xvec_len), dtype=complex)
        x_to_Y[:,:,:,:,idx:idx+Yb_len] = Y_basis
        idx += Yb_len

        x_to_Z = np.zeros((n,n,n,n,xvec_len), dtype=complex)
        x_to_Z[:,:,:,:,idx:idx+Zb_len] = Z_basis
        idx += Zb_len

        if ppt:
            x_to_Z2 = np.zeros((n,n,n,n,xvec_len), dtype=complex)
            x_to_Z2[:,:,:,:,idx:idx+Zb_len] = Z_basis
            idx += Zb_len

        assert idx == xvec_len

        phi_phi = np.zeros((n,n, n,n), dtype=complex)
        for (i, j) in itertools.product(range(n), repeat=2):
            phi_phi[i, i, j, j] = 1
        phi_phi = phi_phi.reshape(n**2, n**2)

        # Cost vector.
        # x = [t, Y.A:Si * Y.A':i * Y.A':j]
        c = np.zeros(xvec_len)
        c[0] = 1

        # tI - tr_A{Y-Z} >= 0
        Fx_1 = -np.trace(x_to_Y - x_to_Z, axis1=0, axis2=2)
        if ppt:
            Fx_1 += np.trace(x_to_Z2, axis1=0, axis2=2)
        for i in xrange(n):
            Fx_1[i, i, 0] = 1

        F0_1 = np.zeros((n, n))

        # Y - Z  >=  |phi><phi|
        Fx_2 = (x_to_Y - x_to_Z).reshape(n**2, n**2, xvec_len)
        if ppt:
            Fx_2 -= x_to_Z2.reshape(n**2, n**2, xvec_len)
        F0_2 = phi_phi

        Fx_3 = x_to_Z.transpose((0,2,1,3,4)).reshape(n**2, n**2, xvec_len)
        F0_3 = np.zeros((n**2, n**2), dtype=complex)

        Fx_list = [Fx_1, Fx_2, Fx_3]
        F0_list = [F0_1, F0_2, F0_3]

        if ppt:
            Fx_4 = x_to_Z2.transpose((1,2,0,3,4)).reshape(n**2, n**2, xvec_len)
            F0_4 = np.zeros((n**2, n**2), dtype=complex)
            Fx_list.append(Fx_4)
            F0_list.append(F0_4)

        (xvec, sdp_stats) = call_sdp(c, Fx_list, F0_list)
        if sdp_stats['status'] != 'optimal':
            raise ArithmeticError(sdp_stats['status'])

        t = xvec[0]
        Y = np.dot(x_to_Y, xvec)
        Z = np.dot(x_to_Z, xvec)
        Z2 = np.dot(x_to_Z2, xvec) if ppt else np.zeros((n,n,n,n))

        # some sanity checks to make sure the output makes sense
        verify_tol=1e-7
        if verify_tol:
            err = linalg.eigvalsh((Y-Z-Z2).reshape(n**2, n**2) - phi_phi)[0]
            if err < -verify_tol: print "WARNING: phi_phi err =", err

            err = linalg.eigvalsh(Z.transpose(0,2,1,3).reshape(n**2, n**2))[0]
            if err < -verify_tol: print "WARNING: R(Z) err =", err

            if ppt:
                err = linalg.eigvalsh(Z2.transpose(1,2,0,3).reshape(n**2, n**2))[0]
                if err < -verify_tol: print "WARNING: R(Z2) err =", err

            maxeig = linalg.eigvalsh(np.trace(Y-Z-Z2, axis1=0, axis2=2))[-1].real
            err = abs(xvec[0] - maxeig)
            if err > verify_tol: print "WARNING: t err =", err

            # make sure it is in S*L(A')
            for mat in self.Sp_basis:
                dp = np.tensordot(Y, mat.conjugate(), axes=[[0, 2], [0, 1]])
                err = linalg.norm(dp)
                if err > 1e-10: print "err:", err
                assert err < 1e-10

        if long_return:
            ret = {}
            for key in [
                    'n', 'x_to_Y', 'x_to_Z',
                    'Fx_1', 'Fx_2', 'Fx_3', 'F0_1', 'F0_2', 'F0_3',
                    'phi_phi', 'c', 't', 'Y', 'Z', 'xvec', 'sdp_stats'
                ]:
                    ret[key] = locals()[key]
            return ret
        else:
            return t

    def szegedy(self, ppt, long_return=False):
        """
        My non-commutative generalization of Schrijver's number.

        min t s.t.
            tI - Tr_A Y \succeq 0
            Y \in S \ot \mathcal{L}
            Y \succeq \Phi
            R(Y) \succeq 0
            optional: R(Y) \in PPT
        """

        (nS, n, _n) = self.S_basis.shape
        assert n == _n

        Y_basis = self._basis_doubly_hermit(self.S_flat)
        Yb_len = Y_basis.shape[4]

        # x = [t, Y.A:Si * Y.A':i * Y.A':j, Z]
        xvec_len = 1 + Yb_len

        idx = 1
        x_to_Y = np.zeros((n,n,n,n,xvec_len), dtype=complex)
        x_to_Y[:,:,:,:,idx:idx+Yb_len] = Y_basis
        idx += Yb_len

        assert idx == xvec_len

        phi_phi = np.zeros((n,n, n,n), dtype=complex)
        for (i, j) in itertools.product(range(n), repeat=2):
            phi_phi[i, i, j, j] = 1
        phi_phi = phi_phi.reshape(n**2, n**2)

        # Cost vector.
        # x = [t, Y.A:Si * Y.A':i * Y.A':j]
        c = np.zeros(xvec_len)
        c[0] = 1

        # tI - tr_A{Y} >= 0
        Fx_1 = -np.trace(x_to_Y, axis1=0, axis2=2)
        for i in xrange(n):
            Fx_1[i, i, 0] = 1

        F0_1 = np.zeros((n, n))

        # Y  >=  |phi><phi|
        Fx_2 = x_to_Y.reshape(n**2, n**2, xvec_len)
        F0_2 = phi_phi

        Fx_3 = x_to_Y.transpose((0,2,1,3,4)).reshape(n**2, n**2, xvec_len)
        F0_3 = np.zeros((n**2, n**2), dtype=complex)

        Fx_list = [Fx_1, Fx_2, Fx_3]
        F0_list = [F0_1, F0_2, F0_3]

        if ppt:
            Fx_4 = x_to_Y.transpose((1,2,0,3,4)).reshape(n**2, n**2, xvec_len)
            F0_4 = np.zeros((n**2, n**2), dtype=complex)
            Fx_list.append(Fx_4)
            F0_list.append(F0_4)

        (xvec, sdp_stats) = call_sdp(c, Fx_list, F0_list)
        if sdp_stats['status'] != 'optimal':
            raise ArithmeticError(sdp_stats['status'])

        t = xvec[0]
        Y = np.dot(x_to_Y, xvec)

        # some sanity checks to make sure the output makes sense
        verify_tol=1e-7
        if verify_tol:
            err = linalg.eigvalsh(Y.reshape(n**2, n**2) - phi_phi)[0]
            if err < -verify_tol: print "WARNING: phi_phi err =", err

            err = linalg.eigvalsh(Y.transpose(0,2,1,3).reshape(n**2, n**2))[0]
            if err < -verify_tol: print "WARNING: R(Y) err =", err

            if ppt:
                err = linalg.eigvalsh(Y.transpose(1,2,0,3).reshape(n**2, n**2))[0]
                if err < -verify_tol: print "WARNING: R(Y) err =", err

            maxeig = linalg.eigvalsh(np.trace(Y, axis1=0, axis2=2))[-1].real
            err = abs(xvec[0] - maxeig)
            if err > verify_tol: print "WARNING: t err =", err

            # make sure it is in S*L(A')
            for mat in self.Sp_basis:
                dp = np.tensordot(Y, mat.conjugate(), axes=[[0, 2], [0, 1]])
                err = linalg.norm(dp)
                if err > 1e-10: print "err:", err
                assert err < 1e-10

        if long_return:
            ret = {}
            for key in [
                    'n', 'x_to_Y',
                    'Fx_1', 'Fx_2', 'Fx_3', 'F0_1', 'F0_2', 'F0_3',
                    'phi_phi', 'c', 't', 'Y', 'xvec', 'sdp_stats'
                ]:
                    ret[key] = locals()[key]
            return ret
        else:
            return t

    def unified_test(self):
        (nS, n, _n) = self.S_basis.shape
        assert n == _n

        psd = {
            'x': lambda Z: Z.transpose((0,2,1,3)).reshape(n**2, n**2),
            '0': np.zeros((n**2, n**2), dtype=complex),
        }

        ppt = {
            'x': lambda Z: Z.transpose((1,2,0,3)).reshape(n**2, n**2),
            '0': np.zeros((n**2, n**2), dtype=complex),
        }

        Y_basis = self._get_Y_basis()
        Y_basis_dh = self._basis_doubly_hermit(self.S_flat)

        a_th = self.lovasz_theta()
        b_th = self.unified(Y_basis, [], [])
        print a_th, b_th
        a_thm = self.schrijver(False)
        b_thm = self.unified(Y_basis, [], [psd])
        print a_thm, b_thm
        a_thm = self.schrijver(True)
        b_thm = self.unified(Y_basis, [], [psd, ppt])
        print a_thm, b_thm
        a_thp = self.szegedy(False)
        b_thp = self.unified(Y_basis_dh, [psd], [])
        print a_thp, b_thp
        a_thp = self.szegedy(True)
        b_thp = self.unified(Y_basis_dh, [psd, ppt], [])
        print a_thp, b_thp

    def unified(self, Y_basis, extra_constraints, extra_vars, long_return=False):
        """
        My non-commutative generalization of Schrijver's number.

        min t s.t.
            tI - Tr_A (Y-Z) \succeq 0
            Y \in S \ot \mathcal{L}
            Y-Z \succeq \Phi
            R(Z) \in \sum( extra_vars )
            R(Y) \in \cap( extra_constraints )
        """

        n = self.n

        Yb_len = Y_basis.shape[4]
        Z_basis = self._basis_doubly_hermit(TensorSubspace.full((n,n)))
        Zb_len = Z_basis.shape[4]

        # x = [t, Y.A:Si * Y.A':i * Y.A':j, Z]
        xvec_len = 1 + Yb_len + len(extra_vars)*Zb_len

        idx = 1
        x_to_Y = np.zeros((n,n,n,n,xvec_len), dtype=complex)
        x_to_Y[:,:,:,:,idx:idx+Yb_len] = Y_basis
        idx += Yb_len

        x_to_Z = []
        for v in extra_vars:
            xZ = np.zeros((n,n,n,n,xvec_len), dtype=complex)
            xZ[:,:,:,:,idx:idx+Zb_len] = Z_basis
            idx += Zb_len
            x_to_Z.append(xZ)

        assert idx == xvec_len

        phi_phi = np.zeros((n,n, n,n), dtype=complex)
        for (i, j) in itertools.product(range(n), repeat=2):
            phi_phi[i, i, j, j] = 1
        phi_phi = phi_phi.reshape(n**2, n**2)

        # Cost vector.
        # x = [t, Y.A:Si * Y.A':i * Y.A':j]
        c = np.zeros(xvec_len)
        c[0] = 1

        # tI - tr_A{Y-Z} >= 0
        Fx_1 = -np.trace(x_to_Y, axis1=0, axis2=2)
        for xZ in x_to_Z:
            Fx_1 += np.trace(xZ, axis1=0, axis2=2)
        for i in xrange(n):
            Fx_1[i, i, 0] = 1
        F0_1 = np.zeros((n, n))

        # Y - Z  >=  |phi><phi|
        Fx_2 = x_to_Y.reshape(n**2, n**2, xvec_len).copy()
        for xZ in x_to_Z:
            Fx_2 -= xZ.reshape(n**2, n**2, xvec_len)
        F0_2 = phi_phi

        Fx_evars = []
        F0_evars = []
        for (xZ, v) in zip(x_to_Z, extra_vars):
            Fx = np.array([ v['x'](z) for z in np.rollaxis(xZ, -1) ], dtype=complex)
            Fx = np.rollaxis(Fx, 0, len(Fx.shape))
            F0 = v['0']
            Fx_evars.append(Fx)
            F0_evars.append(F0)

        Fx_econs = []
        F0_econs = []
        for v in extra_constraints:
            Fx = np.array([ v['x'](y) for y in np.rollaxis(x_to_Y, -1) ], dtype=complex)
            Fx = np.rollaxis(Fx, 0, len(Fx.shape))
            F0 = v['0']
            Fx_econs.append(Fx)
            F0_econs.append(F0)

        Fx_list = [Fx_1, Fx_2] + Fx_evars + Fx_econs
        F0_list = [F0_1, F0_2] + F0_evars + F0_econs

        (xvec, sdp_stats) = call_sdp(c, Fx_list, F0_list)
        if sdp_stats['status'] != 'optimal':
            raise ArithmeticError(sdp_stats['status'])

        t = xvec[0]
        Y = np.dot(x_to_Y, xvec)
        Z_list = [ np.dot(xZ, xvec) for xZ in x_to_Z ]
        Z_sum = np.sum(Z_list, axis=0)

        # some sanity checks to make sure the output makes sense
        verify_tol=1e-7
        if verify_tol:
            err = linalg.eigvalsh((Y-Z_sum).reshape(n**2, n**2) - phi_phi)[0]
            if err < -verify_tol: print "WARNING: phi_phi err =", err

            for (i, (v, Z)) in enumerate(zip(extra_vars, Z_list)):
                M = v['x'](Z) - v['0']
                err = linalg.eigvalsh(M)[0]
                if err < -verify_tol: print "WARNING: R(Z%d) err = %g" % (i, err)

            for (i, v) in enumerate(extra_constraints):
                M = v['x'](Y) - v['0']
                err = linalg.eigvalsh(M)[0]
                if err < -verify_tol: print "WARNING: R(Y) err =", err

            maxeig = linalg.eigvalsh(np.trace(Y-Z_sum, axis1=0, axis2=2))[-1].real
            err = abs(xvec[0] - maxeig)
            if err > verify_tol: print "WARNING: t err =", err

            # make sure it is in S*L(A')
            for mat in self.Sp_basis:
                dp = np.tensordot(Y, mat.conjugate(), axes=[[0, 2], [0, 1]])
                err = linalg.norm(dp)
                if err > 1e-10: print "S err:", err
                assert err < 1e-10

        if long_return:
            ret = {}
            for key in [
                    'n', 'x_to_Y', 'x_to_Z',
                    'phi_phi', 'c', 't', 'Y', 'Z_list', 'xvec', 'sdp_stats'
                ]:
                    ret[key] = locals()[key]
            return ret
        else:
            return t

# Maybe this cannot be computed using a semidefinite program.
#
#    def small_lovasz(self, long_return=False):
#        """
#        Compute the non-commutative generalization of the Lovasz function
#        (non-multiplicative version), using Eq. 5 of arXiv:1002.2514.
#
#        If the long_return option is True, then some extra status and internal
#        quantities are returned.
#        """
#
#        (nSp, n, _n) = self.Sp_basis.shape
#        assert n == _n
#
#        Sp_basis = self.S.perp().hermitian_basis()
#        # x = [t, T:Si]
#        xvec_len = 1 + Sp_basis.shape[2]
#        x_to_Sp = np.concatenate((
#                np.zeros((n,n, 1)),
#                Sp_basis
#            ), axis=2)
#        assert x_to_Sp.shape[2] == xvec_len
#
#        # Cost vector.
#        c = np.zeros(xvec_len)
#        c[0] = -1
#
#        # FIXME - any way to maximize the max eigenvalue?
#        # tI - T >= 0
#        Fx_1 = -x_to_Sp
#        for i in xrange(n):
#            Fx_1[i, i, 0] = 1
#
#        F0_1 = np.zeros((n, n))
#
#        # T + I >= 0
#        Fx_2 = x_to_Sp
#        F0_2 = -np.eye(n)
#
#        (xvec, sdp_stats) = call_sdp(c, (Fx_1, Fx_2), (F0_1, F0_2))
#        if sdp_stats['status'] != 'optimal':
#            raise ArithmeticError(sdp_stats['status'])
#
#        t = xvec[0]
#        T = np.dot(x_to_Sp, xvec)
#
#        theta = t+1
#
#        if long_return:
#            ret = {}
#            for key in ['n', 'x_to_Sp', 'Fx_1', 'Fx_2', 'F0_1', 'F0_2', 'c', 't', 'theta', 'T', 'xvec', 'sdp_stats']:
#                ret[key] = locals()[key]
#            return ret
#        else:
#            return theta

# For testing whether two implementations of _get_Y_basis work the same.
#d = 5
#M = np.random.random((d, d)) + 1j*np.random.random((d, d))
#M2 = np.random.random((d, d)) + 1j*np.random.random((d, d))
#S = TensorSubspace.from_span([ M, M.T.conj(), np.eye(d, d), M2, M2.conj().T ])
#G = NoncommutativeGraph(S)
#print 'get 1'
#yb1 = G._get_Y_basis().transpose(4,0,1,2,3)
#print 'get 2'
#yb2 = G._get_Y_basis_v2().transpose(4,0,1,2,3)
#print 'test'
#for x in yb1:
#    x = x.reshape(d*d, d*d)
#    assert linalg.norm(x - x.conj().T) == 0
#for x in yb2:
#    x = x.reshape(d*d, d*d)
#    assert linalg.norm(x - x.conj().T) == 0
#tb1 = TensorSubspace.from_span(yb1)
#tb2 = TensorSubspace.from_span(yb2)
#print tb1.equiv(tb2)

#if __name__ == "__main__":
#    from qitensor import qubit, qudit
#    ha = qubit('a')
#    hb = qubit('b')
#    S = TensorSubspace.from_span([ (ha*hb).eye() ])
#    G = NoncommutativeGraph(S)
#    print G.lovasz_theta()
#    hc = qudit('c', 5)
#    G2 = NoncommutativeGraph(NoncommutativeGraph.pentagon().S.map(lambda x: hc.O.array(x)))
#    print G2.lovasz_theta()

if __name__ == "__main__":
    from qitensor import qudit

    def rand_graph(spc, num_ops):
        S = TensorSubspace.from_span([ spc.eye() ])
        for i in range(num_ops):
            M = spc.O.random_array()
            S |= TensorSubspace.from_span([ M, M.H ])
        return S

    cvxopt.solvers.options['show_progress'] = False
    # Unfortunately, Schrijver doesn't converge well.
    cvxopt.solvers.options['abstol'] = float(1e-5)
    cvxopt.solvers.options['reltol'] = float(1e-5)

    n = 3
    ha = qudit('a', n)

    S = rand_graph(ha, 3)
    #S = TensorSubspace.from_span([ ha.eye() ])
    print S

    NoncommutativeGraph(S).unified_test()

# If this module is run from the command line, run the doctests.
if __name__ == "__main__":
    # Doctests require not getting progress messages from SDP solver.
    cvxopt.solvers.options['show_progress'] = False

    print "Running doctests."

    import doctest
    doctest.testmod()
