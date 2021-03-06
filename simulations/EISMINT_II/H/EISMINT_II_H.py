from fenics          import *
from varglas.solvers import HybridTransientSolver
from varglas.helper  import default_config
from varglas.model   import Model

set_log_active(False)

parameters['form_compiler']['quadrature_degree'] = 2
parameters['form_compiler']['precision']         = 30
parameters['form_compiler']['optimize']          = True
parameters['form_compiler']['cpp_optimize']      = True
parameters['form_compiler']['representation']    = 'quadrature'

mesh = Mesh('meshes/circle.xml')

thklim = 1.0

config = default_config()
config['log']                          = True
config['log_history']                  = True
config['mode']                         = 'transient'
config['model_order']                  = 'L1L2'
config['output_path']                  = './EISMINT_H_Results/'
config['t_start']                      = 0.0
config['t_end']                        = 100000.0
config['time_step']                    = Constant(250.0)
config['periodic_boundary_conditions'] = False
config['velocity']['poly_degree']      = 2
config['enthalpy']['on']               = True
config['enthalpy']['N_T']              = 8
config['free_surface']['on']           = True
config['free_surface']['thklim']       = thklim
config['balance_velocity']['on']       = False
config['velocity']['transient_beta']   = 'eismint_H'

model = Model(config)
model.set_mesh(mesh)

# GEOMETRY AND INPUT DATA
class Surface(Expression):
  def eval(self,values,x):
    values[0] = thklim
S = Surface(element=model.Q.ufl_element())

class Bed(Expression):
  def eval(self,values,x):
    values[0] = 0
B = Bed(element=model.Q.ufl_element())

class Beta(Expression):
  def eval(self,values,x):
    values[0] = sqrt(1e9)
beta = Beta(element=model.Q.ufl_element())

class Adot(Expression):
  Rel = 450000
  s   = 1e-5
  def eval(self,values,x):
    #values[0] = 0.3
    values[0] = min(0.5,self.s*(self.Rel-sqrt(x[0]**2 + x[1]**2)))
adot = Adot(element=model.Q.ufl_element())

class SurfaceTemperature(Expression):
  Tmin = 238.15
  St   = 1.67e-5
  def eval(self,values,x):
    values[0] = self.Tmin + self.St*sqrt(x[0]**2 + x[1]**2)
T_s = SurfaceTemperature(element=model.Q.ufl_element())

model.set_geometry(S, B, deform=False)
model.initialize_variables()

model.init_adot(adot)
model.init_beta(beta)
model.init_T_surface(T_s)
model.init_H(thklim)
model.init_H_bounds(thklim, 1e4)
model.init_q_geo(model.ghf)

model.eps_reg = 1e-10

T = HybridTransientSolver(model, config)
T.solve()
