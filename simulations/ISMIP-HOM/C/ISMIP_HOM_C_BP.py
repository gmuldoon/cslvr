from varglas.model              import Model
from varglas.solvers            import SteadySolver
from varglas.physical_constants import IceParameters
from varglas.helper             import default_nonlin_solver_params, \
                                       default_config
from fenics                     import set_log_active, File, Expression, pi, \
                                       sin, tan

set_log_active(True)

alpha = 0.1 * pi / 180
L     = 40000

nx = 50
ny = 50 
nz = 10

model = Model()
model.generate_uniform_mesh(nx, ny, nz, xmin=0, xmax=L, ymin=0, ymax=L, 
                            generate_pbcs=True)

Surface = Expression('- x[0] * tan(alpha)', alpha=alpha, 
                     element=model.Q.ufl_element())
Bed     = Expression('- x[0] * tan(alpha) - 1000.0', alpha=alpha, 
                     element=model.Q.ufl_element())
Beta    = Expression('sqrt(1000 + 1000 * sin(2*pi*x[0]/L) * sin(2*pi*x[1]/L))',
                     alpha=alpha, L=L, element=model.Q.ufl_element())

model.set_geometry(Surface, Bed, deform=True)
model.set_parameters(IceParameters())
model.calculate_boundaries()
model.initialize_variables()

nonlin_solver_params = default_nonlin_solver_params()
nonlin_solver_params['newton_solver']['linear_solver']  = 'gmres'
nonlin_solver_params['newton_solver']['preconditioner'] = 'hypre_amg'

config = default_config()
config['output_path']                  = './results_BP_L'+str(L)+'/'
config['periodic_boundary_conditions'] = True
config['velocity']['newton_params']    = nonlin_solver_params
config['velocity']['beta0']            = Beta
 
F = SteadySolver(model, config)
F.solve()

File('./results_BP_L'+str(L)+'/ff.pvd') << model.ff


