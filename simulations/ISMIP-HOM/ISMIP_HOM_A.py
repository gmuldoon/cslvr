import timeit
import sys
start=timeit.default_timer()

from cslvr    import *
from fenics   import Point, BoxMesh, Expression, sqrt, pi

alpha = 0.5 * pi / 180 
L     = 40000

p1    = Point(0.0, 0.0, 0.0)
p2    = Point(L,   L,   1)
mesh  = BoxMesh(p1, p2, 10, 10, 4)

model = D3Model(mesh, out_dir = './ISMIP_HOM_A_results/')
model.generate_function_spaces(use_periodic = True)

surface = Expression('- x[0] * tan(alpha)', alpha=alpha,
                     element=model.Q.ufl_element())
bed     = Expression(  '- x[0] * tan(alpha) - 1000.0 + 500.0 * ' \
                     + ' sin(2*pi*x[0]/L) * sin(2*pi*x[1]/L)',
                     alpha=alpha, L=L, element=model.Q.ufl_element())

model.calculate_boundaries()
model.deform_mesh_to_geometry(surface, bed)

model.init_mask(1.0)  # all grounded
model.init_beta(1000)
model.init_b(model.A0(0)**(-1/model.n(0)))
model.init_E(1.0)

#mom = MomentumBP(model, isothermal=True)
#mom = MomentumDukowiczBP(model, isothermal=True)
#mom = MomentumDukowiczStokesReduced(model, isothermal=True)
mom = MomentumDukowiczBrinkerhoffStokes(model, isothermal=True)
mom.solve()

model.save_pvd(model.p,  'p')
model.save_pvd(model.U3, 'U')


elapsed=timeit.default_timer() - start
elapsed=elapsed/60.
print 'It took %f minutes to run %s' % (elapsed, sys.argv[0])
