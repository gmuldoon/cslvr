from fenics                 import *
from dolfin_adjoint         import *
from varglas.io             import get_text, print_text, print_min_max
from varglas.d3model        import D3Model
from varglas.d2model        import D2Model
from varglas.d1model        import D1Model
from varglas.physics        import Physics
from varglas.helper         import VerticalBasis, VerticalFDBasis, \
                                   raiseNotDefined
from copy                   import deepcopy
import numpy                    as np
import matplotlib.pyplot        as plt
import sys
import os


class Energy(Physics):
  """
  Abstract class outlines the structure of an energy conservation.
  """

  def __new__(self, model, *args, **kwargs):
    """
    Creates and returns a new Energy object.
    """
    instance = Physics.__new__(self, model)
    return instance
  
  def __init__(self, model, solve_params=None, transient=False,
               use_lat_bc=False, epsdot_ftn=None):
    """
    """
    # save the starting values, as other algorithms might change the 
    # values to suit their requirements :
    if isinstance(solve_params, dict):
      self.solve_params_s  = deepcopy(solve_params)
    else:
      self.solve_params_s  = solve_params
    self.transient_s       = transient
    self.use_lat_bc_s      = use_lat_bc
    self.epsdot_ftn_s      = epsdot_ftn

    self.T_ini     = self.model.T.copy(True)
    self.W_ini     = self.model.W.copy(True)
    
    self.initialize(model, solve_params, transient,
                    use_lat_bc, epsdot_ftn)
  
  def initialize(self, model, solve_params=None, transient=False,
                 use_lat_bc=False, epsdot_ftn=None, reset=False):
    """ 
    Here we set up the problem, and do all of the differentiation and
    memory allocation type stuff.  Note that any Energy object *must*
    call this method.  See the existing child Energy objects for reference.
    """
    raiseNotDefined()
  
  def make_transient(self, time_step):
    """
    reset the momentum to the original configuration.
    """
    s = "::: RE-INITIALIZING ENERGY PHYSICS WITH TRANSIENT FORM :::"
    print_text(s, self.color())

    self.model.init_time_step(time_step, cls=self)
    
    self.initialize(model=self.model, solve_params=self.solve_params_s,
                    transient = True,
                    use_lat_bc = self.use_lat_bc_s,
                    epsdot_ftn = self.epsdot_ftn_s,
                    reset = True)
  
  def make_steady_state(self):
    """
    reset the momentum to the original configuration.
    """
    s = "::: RE-INITIALIZING ENERGY PHYSICS WITH STEADY-STATE FORM :::"
    print_text(s, self.color())
    
    self.initialize(model=self.model, solve_params=self.solve_params_s,
                    transient = False,
                    use_lat_bc = self.use_lat_bc_s,
                    epsdot_ftn = self.epsdot_ftn_s,
                    reset = True)
 
  def reset(self):
    """
    reset the momentum to the original configuration.
    """
    s = "::: RE-INITIALIZING ENERGY PHYSICS :::"
    print_text(s, self.color())

    self.model.init_T(self.T_ini)
    self.model.init_W(self.W_ini)
    
    self.initialize(model=self.model, solve_params=self.solve_params_s,
                    transient = self.transient_s,
                    use_lat_bc = self.use_lat_bc_s,
                    epsdot_ftn = self.epsdot_ftn_s,
                    reset = True)

  def color(self):
    """
    return the default color for this class.
    """
    return '213'
  
  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    params  = {'solver'              : 'mumps',
               'use_surface_climate' : False}
    return params

  def solve_surface_climate(self):
    """
    Calculates PDD, surface temperature given current model geometry and 
    saves to model.T_surface.
    """
    s    = "::: solving surface climate :::"
    print_text(s, cls=self)
    model = self.model

    T_w   = model.T_w(0)
    S     = model.S.vector().array()
    lat   = model.lat.vector().array()
    lon   = model.lon.vector().array()
   
    # greenland : 
    Tn    = 41.83 - 6.309e-3*S - 0.7189*lat - 0.0672*lon + T_w

    ## antarctica :
    #Tn    = 34.46 - 0.00914*S - 0.27974*lat
    
    # Apply the lapse rate to the surface boundary condition
    model.init_T_surface(Tn, cls=self)
 
  def adjust_adot(self):
    """
    """
    s    = "::: solving surface accumulation :::"
    print_text(s, cls=self)
    model = self.model

    T_w   = model.T_w(0)
    T     = model.T_surface.vector().array()

    adot  = 2.5 * 2**((T-T_w)/10)
    
    shf_dofs = np.where(model.mask.vector().array() == 0.0)[0]
    adot[model.shf_dofs] = -100

    model.init_adot(adot, cls=self)
  
  def form_obj_ftn(self, kind='abs'):
    """
    Forms and returns an objective functional for use with adjoint.
    Saves to self.J.
    """
    s   = "::: forming water-optimization cost functional :::"
    print_text(s, self.color())

    model    = self.model
    theta    = self.theta
    thetam   = model.theta
    dGnd     = model.dBed_g
    theta_m  = model.theta_melt
    L        = model.L
    theta_c  = theta_m + 0.03*L
   
    if kind == 'TV': 
      self.J   = sqrt((theta  - theta_c)**2 + 1e-15) * dGnd
      self.Jp  = sqrt((thetam - theta_c)**2 + 1e-15) * dGnd
      s   = "::: forming TV objective functional :::"
    elif kind == 'L2': 
      self.J   = 0.5 * (theta  - theta_c)**2 * dGnd
      self.Jp  = 0.5 * (thetam - theta_c)**2 * dGnd
      s   = "::: forming L2 objective functional :::"
    elif kind == 'abs': 
      self.J   = abs(theta  - theta_c) * dGnd
      self.Jp  = abs(thetam - theta_c) * dGnd
      s   = "::: forming absolute value objective functional :::"
    else:
      s = ">>> ADJOINT OBJECTIVE FUNCTIONAL MAY BE 'TV', 'L2' " + \
          "or 'abs', NOT '%s' <<<" % kind
      print_text(s, 'red', 1)
      sys.exit(1)
    print_text(s, self.color())

  def calc_misfit(self):
    """
    Calculates the misfit, 
    """
    s   = "::: calculating misfit L-infty norm ||theta - theta_c|| :::"
    print_text(s, cls=self)

    model   = self.model
    theta   = model.theta
    theta_m = model.theta_melt
    L       = model.L(0)

    # set up functions for surface (s) and current objective (o) :
    theta_s = Function(model.Q)
    theta_o = Function(model.Q)

    # calculate L_inf norm :
    theta_v   = theta.vector().array()
    theta_c_v = theta_m.vector().array() + 0.03 * L
    theta_o.vector().set_local(np.abs(theta_v - theta_c_v))
    theta_o.vector().apply('insert')
 
    # apply difference over only grounded surface :
    bc_theta  = DirichletBC(model.Q, theta_o, model.ff, model.GAMMA_B_GND)
    bc_theta.apply(theta_s.vector())

    # calculate L_inf vector norm :
    D        = MPI.max(mpi_comm_world(), theta_s.vector().max())

    s    = "||theta - theta_c|| : %.3E" % D
    print_text(s, '208', 1)
    return D
  
  def calc_functionals(self):
    """
    Used to facilitate printing the objective function in adjoint solves.
    """
    R = assemble(self.Rp, annotate=False)
    J = assemble(self.Jp, annotate=False)
    print_min_max(R, 'R', cls=self)
    print_min_max(J, 'J', cls=self)
    return (R, J)
  
  def calc_obj(self):
    """
    Used to facilitate printing the objective function in adjoint solves.
    """
    J = assemble(self.Jp, annotate=False)
    print_min_max(J, 'J', cls=self)
    return J

  def solve(self, annotate=True, params=None):
    """ 
    Perform the Newton solve of the energy equation.
    """
    raiseNotDefined()


class Enthalpy(Energy):
  """
  """ 
  def initialize(self, model, solve_params=None, transient=False,
                 use_lat_bc=False, epsdot_ftn=None, reset=False):
    """ 
    Set up energy equation residual. 
    """
    self.transient = transient

    s    = "::: INITIALIZING ENTHALPY PHYSICS :::"
    print_text(s, cls=self)

    #if type(model) != D3Model:
    #  s = ">>> Enthalpy REQUIRES A 'D3Model' INSTANCE, NOT %s <<<"
    #  print_text(s % type(model) , 'red', 1)
    #  sys.exit(1)
   
    # set solver parameters : 
    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params
    
    # set the function that returns the strain-rate tensor, default is full :
    if epsdot_ftn == None:
      self.strain_rate_tensor = self.default_strain_rate_tensor
    else:
      self.strain_rate_tensor = epsdot_ftn

    r             = model.r
    mesh          = model.mesh
    V             = model.Q3
    Q             = model.Q
    n             = model.n
    eps_reg       = model.eps_reg
    T             = model.T
    W             = model.W
    T_m           = model.T_melt
    Mb            = model.Mb
    L             = model.L
    T_w           = model.T_w
    gamma         = model.gamma
    S             = model.S
    B             = model.B
    H             = S - B
    x             = model.x
    R             = model.R
    U             = model.U3
    u             = model.u
    v             = model.v
    w             = model.w
    eps_reg       = model.eps_reg
    g             = model.g
    alpha         = model.alpha
    beta          = model.beta
    rhoi          = model.rhoi
    rhow          = model.rhow
    kw            = model.kw
    cw            = model.cw
    L             = model.L
    T_surface     = model.T_surface
    theta_surface = model.theta_surface
    theta_float   = model.theta_float
    theta_app     = model.theta_app
    theta_m       = model.theta_melt
    q_geo         = model.q_geo
    thetahat      = model.thetahat
    uhat          = model.uhat
    vhat          = model.vhat
    what          = model.what
    mhat          = model.mhat
    spy           = model.spy
    h             = model.h
    ds            = model.ds
    dSrf          = model.dSrf
    dBed_g        = model.dBed_g
    dBed_f        = model.dBed_f
    dBed          = model.dBed
    dLat_t        = model.dLat_t
    dx            = model.dx
    dx_f          = model.dx_f
    dx_g          = model.dx_g
    E_shf         = model.E_shf
    E_gnd         = model.E_gnd
    N             = model.N
    
    # define test and trial functions : 
    psi    = TestFunction(Q)
    dtheta = TrialFunction(Q)
    theta  = Function(Q, name='energy.theta')
    theta0 = Function(Q, name='energy.theta0')

    # initialize the boundary conditions, if we have not already :
    if not reset:
      # pressure melting point, never annotate for initial guess :
      model.solve_hydrostatic_pressure(annotate=False, cls=self)
      self.calc_T_melt(annotate=False)

      T_s_v   = T_surface.vector().array()
      T_m_v   = T_m.vector().array()
      theta_s = 146.3*T_s_v + 7.253/2.0*T_s_v**2
      theta_f = 146.3*T_m_v + 7.253/2.0*T_m_v**2
     
      # Surface boundary condition :
      s = "::: calculating energy boundary conditions :::"
      print_text(s, cls=self)

      # initialize the boundary conditions :
      model.init_theta_surface(theta_s, cls=self)
      model.init_theta_app(theta_s,     cls=self)
      model.init_theta_float(theta_f,   cls=self)
      
    # strain-rate :
    epsdot  = self.effective_strain_rate(U) + eps_reg

    # thermal properties :
    T_c     = 263.15
    #theta_c = 146.3*T_c + 7.253/2.0*T_c**2
    #theta_w = 0.01*L + theta_m
    W_w     = (theta - theta_m)/L
    T_w     = (-146.3 + sqrt(146.3**2 + 2*7.253*theta)) / 7.253
    self.T  = conditional( lt(T, T_m), T_w, T_m)
    self.W  = conditional( lt(T, T_m), 0.0, W_w)
      
    # discontinuous properties :
    #a_T     = conditional( lt(theta, theta_c), 1.1384496e-5, 5.45e10)
    #Q_T     = conditional( lt(theta, theta_c), 6e4,          13.9e4)
    #W_T     = conditional( lt(theta, theta_w), W_w,          0.01)
    #W_c     = conditional( le(theta, theta_m), 0.0,          1.0)
    #W_a     = conditional( le(theta, theta_m), 0.0,          W_w)
    a_T     = conditional( lt(T, T_c),  1.1384496e-5, 5.45e10)
    Q_T     = conditional( lt(T, T_c),  6e4,          13.9e4)
    W_T     = conditional( lt(W, 0.01), W,            0.01)
    #W_T     = conditional( lt(W_t, 0.00), 0.0,        W_t)

    # viscosity and strain-heating :
    #b_shf   = ( E_shf*a_T*(1 + 181.25*W_c*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    #b_gnd   = ( E_gnd*a_T*(1 + 181.25*W_c*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    #eta_shf = 0.5 * b_shf * epsdot**((1-n)/(2*n))
    #eta_gnd = 0.5 * b_gnd * epsdot**((1-n)/(2*n))
    #Q_s_gnd = 4 * eta_gnd * epsdot
    #Q_s_shf = 4 * eta_shf * epsdot
    b_shf   = ( E_shf*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    b_gnd   = ( E_gnd*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    eta_shf = 0.5 * b_shf * epsdot**((1-n)/(2*n))
    eta_gnd = 0.5 * b_gnd * epsdot**((1-n)/(2*n))
    Q_s_gnd = 4 * eta_gnd * epsdot
    Q_s_shf = 4 * eta_shf * epsdot
    
    # coefficient for diffusion of ice-water mixture -- no water diffusion :
    k_c   = conditional( lt(T, T_m), 1.0, 1e-3)

    # thermal conductivity and heat capacity (Greve and Blatter 2009) :
    ki    = 9.828 * exp(-0.0057*T)
    ci    = 146.3 + 7.253*T
    
    # bulk properties :
    k     =  (1 - W)*ki   + W*kw     # bulk thermal conductivity
    c     =  (1 - W)*ci   + W*cw     # bulk heat capacity
    rho   =  (1 - W)*rhoi + W*rhow   # bulk density
    k     =  spy * k_c * k           # convert to J/(a*m*K)
    kappa =  k / (rho*c)             # bulk thermal diffusivity

    # frictional heating :
    q_fric = beta * inner(U,U)

    # basal heat-flux natural boundary condition :
    Mb   = (q_geo + q_fric - k * dot(grad(T_m), N)) / (rho * L)
    Wmax = Constant(1.0)
    #mdot = W_c * (W_w + DOLFIN_EPS) / (Wmax + DOLFIN_EPS) * Mb * rho * L
    mdot = Mb * rho * L
    g_b  = q_geo + q_fric - alpha * mdot

    # configure the module to run in steady state :
    if not transient:
      s = "    - using steady-state formulation -"
      print_text(s, cls=self)
      # skewed test function in areas with high velocity :
      Unorm  = sqrt(dot(U, U) + DOLFIN_EPS)
      PE     = Unorm*h/(2*kappa)
      tau    = 1/tanh(PE) - 1/PE
      psihat = psi + h*tau/(2*Unorm) * dot(U, grad(psi))
      
      # cannonical form, same as below :
      #psihat = h*tau/(2*Unorm) * dot(U, grad(psi))
      #
      ## residual :
      #delta  = + rho * dot(U, grad(dtheta)) * psihat * dx \
      #         - div(rho * kappa * grad(dtheta)) * psihat * dx \
      #         - Q_s_gnd * psihat * dx_g \
      #         - Q_s_shf * psihat * dx_f \
      #
      ## galerkin formulation :
      #F      = + rho * dot(U, grad(dtheta)) * psi * dx \
      #         + rho * kappa * dot(grad(psi), grad(dtheta)) * dx \
      #         - (q_geo + q_fric) * psi * dBed_g \
      #         - Q_s_gnd * psi * dx_g \
      #         - Q_s_shf * psi * dx_f \
      #         + delta

      #theta_a = lhs(F)
      #theta_L = rhs(F)

      # galerkin formulation :
      theta_a = + rho * dot(U, grad(dtheta)) * psihat * dx \
                - dot(grad(k/c), grad(dtheta)) * psi * dx \
                + k/c * dot(grad(psi), grad(dtheta)) * dx \
      
      theta_L = + g_b * psi * dBed_g \
                + Q_s_gnd * psi * dx_g \
                + Q_s_shf * psi * dx_f

      self.theta_a = theta_a
      self.theta_L = theta_L
      self.nrg_F   = self.theta_a - self.theta_L
      
    # configure the module to run in transient mode :
    else:
      s = "    - using transient formulation -"
      print_text(s, cls=self)
      dt      = model.time_step
   
      # we need to initialize the previous time step, so I hope you've 
      # either called model.init_theta() or model.init_T() :
      model.assign_variable(theta0, model.theta, cls=self)

      # Skewed test function.  Note that vertical velocity has 
      # the mesh velocity subtracted from it.
      Unorm  = sqrt(dot(U, U) + DOLFIN_EPS)
      PE     = Unorm*h/(2*kappa)
      tau    = 1/tanh(PE) - 1/PE
      psihat = psi + h*tau/(2*Unorm) * dot(U, grad(psi))

      nu = 0.5
      # Crank Nicholson method
      thetamid = nu*dtheta + (1 - nu)*theta0
      
      # implicit system (linearized) for energy at time theta_{n+1}
      theta_a = + rho * (dtheta - theta0) / dt * psi * dx \
                + rho * dot(U, grad(thetamid)) * psihat * dx \
                - dot(grad(k/c), grad(thetamid)) * psi * dx \
                + k/c * dot(grad(psi), grad(thetamid)) * dx \
      
      theta_L = + g_b * psi * dBed_g \
                + Q_s_gnd * psi * dx_g \
                + Q_s_shf * psi * dx_f

      self.theta_a = lhs(theta_a - theta_L)
      self.theta_L = rhs(theta_a - theta_L)
    
    # surface boundary condition : 
    self.theta_bc = []
    self.theta_bc.append( DirichletBC(Q, theta_surface, 
                                      model.ff, model.GAMMA_S_GND) )
    self.theta_bc.append( DirichletBC(Q, theta_surface,
                                      model.ff, model.GAMMA_S_FLT) )
    self.theta_bc.append( DirichletBC(Q, theta_surface, 
                                      model.ff, model.GAMMA_U_GND) )
    self.theta_bc.append( DirichletBC(Q, theta_surface,
                                      model.ff, model.GAMMA_U_FLT) )
    
    # apply T_melt conditions of portion of ice in contact with water :
    self.theta_bc.append( DirichletBC(Q, theta_float, 
                                      model.ff, model.GAMMA_B_FLT) )
    self.theta_bc.append( DirichletBC(Q, theta_float, 
                                      model.ff, model.GAMMA_L_UDR) )
    
    # apply lateral ``divide'' boundaries if desired : 
    if use_lat_bc:
      s = "    - using divide-lateral boundary conditions -"
      print_text(s, cls=self)
      self.theta_bc.append( DirichletBC(Q, model.theta_app,
                                        model.ff, model.GAMMA_L_DVD) )
  
    # Jacobian : 
    self.nrg_Jac = derivative(self.nrg_F, theta, dtheta)

    self.theta   = theta
    self.theta0  = theta0
    self.mdot    = mdot
    self.c       = c
    self.k       = k
    self.rho     = rho
    self.kappa   = kappa
    self.q_fric  = q_fric
    self.Q_s_gnd = Q_s_gnd
    self.Q_s_shf = Q_s_shf
    self.Wmax    = Wmax
  
  def default_strain_rate_tensor(self, U):
    """
    return the default unsimplified-strain-rate tensor for velocity <U>.
    """
    u,v,w  = U
    epi    = 0.5 * (grad(U) + grad(U).T)
    return epi
  
  def effective_strain_rate(self, U):
    """
    return the effective strain rate squared.
    """
    epi    = self.strain_rate_tensor(U)
    ep_xx  = epi[0,0]
    ep_yy  = epi[1,1]
    ep_zz  = epi[2,2]
    ep_xy  = epi[0,1]
    ep_xz  = epi[0,2]
    ep_yz  = epi[1,2]
    
    # Second invariant of the strain rate tensor squared
    epsdot = 0.5 * (+ ep_xx**2 + ep_yy**2 + ep_zz**2) \
                    + ep_xy**2 + ep_xz**2 + ep_yz**2
    return epsdot
    
  def calc_T_melt(self, annotate=True):
    """
    Calculates pressure-melting point in model.T_melt.
    """
    s    = "::: calculating pressure-melting temperature :::"
    print_text(s, cls=self)

    model = self.model

    gamma = model.gamma
    T_w   = model.T_w
    p     = model.p

    Tm = project(T_w - gamma * p, annotate=annotate)
    model.assign_variable(model.T_melt, Tm, cls=self)

    Tm_v    = Tm.vector().array()
    theta_m = 146.3*Tm_v + 7.253/2.0*Tm_v**2
    model.assign_variable(model.theta_melt, theta_m, cls=self)

  def solve_divide(self, init=False, annotate=False):
    """
    """
    s    = "::: calculating energy over lateral boundaries :::"
    print_text(s, cls=self)

    model   = self.model
    
    theta   = self.theta
    c       = self.c
    k       = self.k
    rho     = self.rho
    kappa   = self.kappa
    q_fric  = self.q_fric
    Q_s_gnd = self.Q_s_gnd
    Q_s_shf = self.Q_s_shf

    theta_s = model.theta_surface
    theta_f = model.theta_float
    theta_m = model.theta_melt
    L       = model.L
    R       = model.R
    n       = model.n
    E_shf   = model.E_shf
    E_gnd   = model.E_gnd
    T_m     = model.T_melt
    T       = model.T
    W       = model.W
    dx      = model.dx
    dBed_g  = model.dBed_g
    dLat_d  = model.dLat_d
    dLat_t  = model.dLat_t
    dx      = model.dx
    dx_f    = model.dx_f
    dx_g    = model.dx_g
    u       = model.u
    v       = model.v
    w       = model.w
    q_geo   = model.q_geo
    beta    = model.beta
    alpha   = model.alpha
    h       = model.h
    N       = model.N
    U       = as_vector([u,v,w])

    # solve for tangential component of velocity over the 'divides' :
    phi  = TestFunction(model.V)
    du   = TrialFunction(model.V)
    U_t  = U - dot(U, N)*N
    a_n  = inner(du,  phi) * dLat_d
    L_n  = inner(U_t, phi) * dLat_d
    A_n  = assemble(a_n, keep_diagonal=True, annotate=annotate)
    B_n  = assemble(L_n, annotate=annotate)
    A_n.ident_zeros()
    U_t  = Function(model.V)
    solve(A_n, U_t.vector(), B_n, 'cg', 'amg', annotate=annotate)

    # basis functions for thermal regime over the lateral boundaries :
    dtheta  = TrialFunction(model.Q)
    psi     = TestFunction(model.Q)
    theta   = Function(model.Q)

    # thermal properties :
    T_c     = 263.15
    theta_c = 146.3*T_c + 7.253/2.0*T_c**2
    theta_w = 0.01*L + theta_m
    W_w     = (theta - theta_m)/L
    T_w     = (-146.3 + sqrt(146.3**2 + 2*7.253*theta)) / 7.253

    # discontinuous properties :
    #a_T     = conditional( lt(theta, theta_c), 1.1384496e-5, 5.45e10)
    #Q_T     = conditional( lt(theta, theta_c), 6e4,          13.9e4)
    #W_T     = conditional( lt(theta, theta_w), W_w,          0.01)
    #W_c     = conditional( le(theta, theta_m), 0.0,          1.0)
    #W_a     = conditional( le(theta, theta_m), 0.0,          W_w)
    a_T     = conditional( lt(T, T_c),  1.1384496e-5, 5.45e10)
    Q_T     = conditional( lt(T, T_c),  6e4,          13.9e4)
    W_T     = conditional( lt(W, 0.01), W,            0.01)

    # viscosity and strain-heating :
    epsdot  = self.effective_strain_rate(U_t) + model.eps_reg
    #b_shf   = ( E_shf*a_T*(1 + 181.25*W_c*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    #b_gnd   = ( E_gnd*a_T*(1 + 181.25*W_c*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    #eta_shf = 0.5 * b_shf * epsdot**((1-n)/(2*n))
    #eta_gnd = 0.5 * b_gnd * epsdot**((1-n)/(2*n))
    #Q_s_gnd = 4 * eta_gnd * epsdot
    #Q_s_shf = 4 * eta_shf * epsdot
    b_shf   = ( E_shf*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    b_gnd   = ( E_gnd*a_T*(1 + 181.25*W_T)*exp(-Q_T/(R*T)) )**(-1/n)
    eta_shf = 0.5 * b_shf * epsdot**((1-n)/(2*n))
    eta_gnd = 0.5 * b_gnd * epsdot**((1-n)/(2*n))
    Q_s_gnd = 4 * eta_gnd * epsdot
    Q_s_shf = 4 * eta_shf * epsdot
    
    # frictional heating :
    q_fric = beta * inner(U_t, U_t)

    # basal heat-flux natural boundary condition :
    Mb   = (q_geo + q_fric - k * dot(grad(T_m), N)) / (rho * L)
    mdot = Mb * rho * L
    g_b  = q_geo + q_fric - alpha * mdot
      
    # SUPG :
    Unorm  = sqrt(dot(U_t, U_t) + 1e-15)
    PE     = Unorm*h/(2*kappa)
    tau    = 1/tanh(PE) - 1/PE
    psihat = psi + h*tau/(2*Unorm) * dot(U_t, grad(psi))
    
    # galerkin formulation :
    theta_a = + rho * dot(U_t, grad(dtheta)) * psihat * dx \
              - dot(grad(k/c), grad(dtheta)) * psi * dx \
              + k/c * dot(grad(psi), grad(dtheta)) * dx \
    
    theta_L = + g_b * psi * dBed_g \
              + Q_s_gnd * psi * dx_g \
              + Q_s_shf * psi * dx_f

    #nrg_F = theta_a - theta_L
    
    #nrg_Jac = derivative(nrg_F, theta, dtheta)

    # surface boundary condition : 
    theta_bc = []
    theta_bc.append( DirichletBC(model.Q, theta_s,
                                 model.ff, model.GAMMA_S_GND) )
    theta_bc.append( DirichletBC(model.Q, theta_s,
                                 model.ff, model.GAMMA_S_FLT) )
    theta_bc.append( DirichletBC(model.Q, theta_s,
                                 model.ff, model.GAMMA_U_GND) )
    theta_bc.append( DirichletBC(model.Q, theta_s,
                                 model.ff, model.GAMMA_U_FLT) )
    
    # apply T_w conditions of portion of ice in contact with water :
    theta_bc.append( DirichletBC(model.Q, theta_f,
                                 model.ff, model.GAMMA_B_FLT) )
    theta_bc.append( DirichletBC(model.Q, theta_f, 
                                 model.ff, model.GAMMA_L_UDR) )
   
    # solve the system :
    #nparams = {'newton_solver' : {'linear_solver'            : 'gmres',
    #                              'preconditioner'           : 'amg',
    #                              'relative_tolerance'       : 1e-9,
    #                              'relaxation_parameter'     : 1.0,
    #                              'maximum_iterations'       : 10,
    #                              'error_on_nonconvergence'  : False}}
    #solve(nrg_F == 0, theta, J = nrg_Jac, bcs = theta_bc,
    #      annotate = annotate, solver_parameters = nparams)
    solve(theta_a == theta_L, theta, theta_bc,
          solver_parameters = self.solve_params['solver'], annotate=annotate)
    model.assign_variable(model.theta_app, theta, cls=self)

    if init:
      # temperature solved with quadradic formula, using expression for c : 
      s = "::: calculating initial temperature :::"
      print_text(s, cls=self)
      theta_v  = theta.vector().array()
      T_n_v    = (-146.3 + np.sqrt(146.3**2 + 2*7.253*theta_v)) / 7.253
      T_v      = T_n_v.copy()
      
      # update temperature for wet/dry areas :
      T_melt_v     = model.T_melt.vector().array()
      theta_melt_v = model.theta_melt.vector().array()
      warm         = theta_v >= theta_melt_v
      cold         = theta_v <  theta_melt_v
      T_v[warm]    = T_melt_v[warm]
      model.assign_variable(model.T, T_v, cls=self)
      
      # water content solved diagnostically :
      s = "::: calculating initial water content :::"
      print_text(s, cls=self)
      W_v  = (theta_v - theta_melt_v) / model.L(0)
      
      # update water content :
      W_v[W_v < 0.0]  = 0.0   # no water where frozen, please.
      model.assign_variable(model.W0, W_v, cls=self, save=False)
      model.assign_variable(model.W,  W_v, cls=self)

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    params  = {'solver' : {'linear_solver'       : 'gmres',
                           'preconditioner'      : 'amg'},
               'use_surface_climate' : False}
    return params
  
  def solve(self, annotate=False):
    """ 
    Solve the energy equations, saving enthalpy to model.theta, temperature 
    to model.T, and water content to model.W.
    """
    model = self.model
    
    # update the surface climate if desired :
    if self.solve_params['use_surface_climate']:
      self.solve_surface_climate()
    
    # solve the energy equation :
    s    = "::: solving energy :::"
    print_text(s, cls=self)

    #aw        = assemble(self.theta_a, annotate=annotate)
    #Lw        = assemble(self.theta_L, annotate=annotate)
    #for bc in self.theta_bc:
    #  bc.apply(aw, Lw, annotate=annotate)
    #theta_solver = KrylovSolver(self.solve_params['solver'])
    #theta_solver.solve(aw, self.theta.vector(), Lw, annotate=annotate)
    solve(self.theta_a == self.theta_L, self.theta, self.theta_bc,
          solver_parameters = self.solve_params['solver'], annotate=annotate)

    #nparams = {'newton_solver' : {'linear_solver'            : 'gmres',
    #                              'preconditioner'           : 'amg',
    #                              'relative_tolerance'       : 1e-9,
    #                              'relaxation_parameter'     : 1.0,
    #                              'maximum_iterations'       : 10,
    #                              'error_on_nonconvergence'  : False}}
    #solve(self.nrg_F == 0, self.theta, J=self.nrg_Jac, bcs=self.theta_bc,
    #      annotate=annotate, solver_parameters=nparams)
    
    # update the model variable :
    model.assign_variable(model.theta, self.theta, annotate=annotate, cls=self)

    # update the previous energy if solving the transient equation :
    if self.transient:
      model.assign_variable(self.theta0, self.theta, cls=self,
                            annotate=annotate)

    # update the temperature and water content for other physics :
    self.partition_energy(annotate=annotate)

  def partition_energy(self, annotate=False):
    """
    solve for the water content model.W and temperature model.T.
    """
    # temperature solved with quadradic formula, using expression for c : 
    s = "::: calculating temperature :::"
    print_text(s, cls=self)
    
    model      = self.model
    T          = model.T
    W          = model.W
    W0         = model.W0
    theta      = model.theta
    theta_melt = model.theta_melt
    T_melt     = model.T_melt
    L          = model.L
    c          = self.c
    
    # temperature is a quadradic function of energy :
    theta_v  = theta.vector().array()
    T_n_v    = (-146.3 + np.sqrt(146.3**2 + 2*7.253*theta_v)) / 7.253
    T_v      = T_n_v.copy()
    
    # correct for the pressure-melting point :
    T_melt_v     = T_melt.vector().array()
    theta_melt_v = theta_melt.vector().array()
    warm         = theta_v >= theta_melt_v
    cold         = theta_v <  theta_melt_v
    T_v[warm]    = T_melt_v[warm]
    model.assign_variable(T, T_v, cls=self)
    
    # water content solved diagnostically :
    s = "::: calculating water content :::"
    print_text(s, cls=self)
    W_v  = (theta_v - theta_melt_v) / L(0)
    
    # update water content :
    W_v[W_v < 0.0]  = 0.0    # no water where frozen, please.
    model.assign_variable(W0,  W,    cls=self, save=False) # never save
    model.assign_variable(W,   W_v,  cls=self)
   
    # NOTE: to get annotation to work, something similar to this must be done,
    #       right now, this doesn't work : 
    #W_w     = (self.theta - theta_melt)/L
    #T_w     = (-146.3 + sqrt(146.3**2 + 2*7.253*self.theta)) / 7.253
    #T_n  = conditional( lt(T, T_melt), T_w, T_melt)
    #W_n  = conditional( lt(T, T_melt), 0.0, W_w)

    #W_n = project(W_n, annotate=annotate)
    #model.W.assign(W_n, annotate=annotate)
    ##model.assign_variable(W0, W,   cls=self, annotate=annotate, save=False)
    ##model.assign_variable(W,  W_n, cls=self, annotate=annotate)

    #T_n = project(T_n, annotate=annotate)
    #model.T.assign(T_n, annotate=annotate)
    ##model.assign_variable(T,  T_n, cls=self, annotate=annotate)

  def optimize_water_flux(self, max_iter, method='ipopt', adj_callback=None):
    """
    determine the correct basal-water flux.
    """
    s    = '::: optimizing for water-flux in %i maximum iterations :::'
    print_text(s % max_iter, cls=self)

    model = self.model

    # starting time :
    t0   = time()

    # need this for the derivative callback :
    global counter
    counter = 0 
    
    # functional lists to be populated :
    global Rs, Js, Ds
    #Rs = []
    Js = []
    Ds = []
    
    # now solve the control optimization problem : 
    s    = "::: starting adjoint-control optimization with method '%s' :::"
    print_text(s % method, cls=self)
    
    def eval_cb(I, alpha):
      s    = '::: adjoint objective eval post callback function :::'
      print_text(s, cls=self)
      print_min_max(I,     'I',     cls=self)
      print_min_max(alpha, 'alpha', cls=self)
    
    # objective gradient callback function :
    def deriv_cb(I, dI, alpha):
      global counter, Rs, Js
      if method == 'ipopt':
        s0    = '>>> '
        s1    = 'iteration %i (max %i) complete'
        s2    = ' <<<'
        text0 = get_text(s0, 'red', 1)
        text1 = get_text(s1 % (counter, max_iter), 'red')
        text2 = get_text(s2, 'red', 1)
        if MPI.rank(mpi_comm_world())==0:
          print text0 + text1 + text2
        counter += 1
      s    = '::: adjoint obj. gradient post callback function :::'
      print_text(s, cls=self)
      print_min_max(dI,    'dI/dalpha', cls=self)
      
      # update the DA current velocity to the model for evaluation 
      # purposes only; the model.assign_variable function is 
      # annotated for purposes of linking physics models to the adjoint
      # process :
      theta_opt = DolfinAdjointVariable(model.theta).tape_value()
      model.init_theta(theta_opt, cls=self)

      # print functional values :
      model.alpha.assign(alpha, annotate=False)
      #ftnls = self.calc_functionals()
      J     = self.calc_obj()
      D     = self.calc_misfit()

      # functional lists to be populated :
      #Rs.append(ftnls[0])
      #Js.append(ftnls[1])
      Js.append(J)
      Ds.append(D)

      # call that callback, if you want :
      if adj_callback is not None:
        adj_callback(I, dI, alpha)
    
    # solve the momentum equations with annotation enabled :
    s    = '::: solving forward problem for dolfin-adjoint annotatation :::'
    print_text(s, cls=self)
    self.solve(annotate=True)
   
    # get the cost, regularization, and objective functionals :
    I = self.J
    try:
      I += self.R
    except AttributeError:
      print_text('    - not using regularization -', cls=self)

    # define the control variable :    
    m = Control(model.alpha, value=model.alpha)

    # state the minimization problem :
    F = ReducedFunctional(Functional(I), m, eval_cb_post=eval_cb,
                          derivative_cb_post=deriv_cb)

    # optimize with scipy's fmin_l_bfgs_b :
    if method == 'l_bfgs_b': 
      out = minimize(F, method="L-BFGS-B", tol=1e-9, bounds=(0,1),
                     options={"disp"    : True,
                              "maxiter" : max_iter,
                              "gtol"    : 1e-5})
      a_opt = out[0]
    
    # or optimize with IPOpt (preferred) :
    elif method == 'ipopt':
      try:
        import pyipopt
      except ImportError:
        info_red("""You do not have IPOPT and/or pyipopt installed.
                    When compiling IPOPT, make sure to link against HSL,
                    as it is a necessity for practical problems.""")
        raise
      problem = MinimizationProblem(F, bounds=(0,1))
      parameters = {"tol"                : 1e-8,
                    "acceptable_tol"     : 1e-6,
                    "maximum_iterations" : max_iter,
                    "print_level"        : 1,
                    "ma97_order"         : "metis",
                    "ma86_order"         : "metis",
                    "linear_solver"      : "ma57"}
      solver = IPOPTSolver(problem, parameters=parameters)
      a_opt  = solver.solve()
    
    # let's see it :
    print_min_max(a_opt, 'a_opt')

    # make the optimal control variable available :
    model.init_alpha(a_opt, cls=self)
    #Control(model.alpha).update(a_opt)  # FIXME: does this work?

    # reset entire dolfin-adjoint state :
    adj_reset()

    # calculate total time to compute
    tf = time()
    s  = tf - t0
    m  = s / 60.0
    h  = m / 60.0
    s  = s % 60
    m  = m % 60
    text = "time to optimize for water flux: %02d:%02d:%02d" % (h,m,s)
    print_text(text, 'red', 1)
    
    # save all the objective functional values : 
    d    = model.out_dir + 'objective_ftnls_history/'
    s    = '::: saving objective functionals to %s :::'
    print_text(s % d, cls=self)
    if model.MPI_rank==0:
      if not os.path.exists(d):
        os.makedirs(d)
      np.savetxt(d + 'time.txt', np.array([tf - t0]))
      #np.savetxt(d + 'Rs.txt',   np.array(Rs))
      np.savetxt(d + 'Js.txt',   np.array(Js))
      np.savetxt(d + 'Ds.txt',   np.array(Ds))

      fig = plt.figure()
      ax  = fig.add_subplot(111)
      #ax.set_yscale('log')
      ax.set_ylabel(r'$\mathscr{J}\left(\theta\right)$')
      ax.set_xlabel(r'iteration')
      ax.plot(np.array(Js), 'r-', lw=2.0)
      plt.grid()
      plt.savefig(d + 'J.png', dpi=200)
      plt.close(fig)

      #fig = plt.figure()
      #ax  = fig.add_subplot(111)
      #ax.set_yscale('log')
      #ax.set_ylabel(r'$\mathscr{R}\left(\alpha\right)$')
      #ax.set_xlabel(r'iteration')
      #ax.plot(np.array(Rs), 'r-', lw=2.0)
      #plt.grid()
      #plt.savefig(d + 'R.png', dpi=200)
      #plt.close(fig)

      fig = plt.figure()
      ax  = fig.add_subplot(111)
      #ax.set_yscale('log')
      ax.set_ylabel(r'$\mathscr{D}\left(\theta\right)$')
      ax.set_xlabel(r'iteration')
      ax.plot(np.array(Ds), 'r-', lw=2.0)
      plt.grid()
      plt.savefig(d + 'D.png', dpi=200)
      plt.close(fig)

  def solve_basal_water_flux(self):
    """
    Solve for the basal-water flux stored in model.Wb_flux.
    """ 
    # calculate melt-rate : 
    s = "::: solving for basal-water flux :::"
    print_text(s, cls=self)
    
    model    = self.model
    alpha    = model.alpha
    Mb       = model.Mb

    wb_f = project( alpha * Mb, annotate=False)
    model.init_Wb_flux(wb_f, cls=self)

  def solve_critical_alpha(self):
    """
    """ 
    # calculate melt-rate : 
    s = "::: solving for critical alpha :::"
    print_text(s, cls=self)
    
    model    = self.model
    q_geo    = model.q_geo
    Mb       = model.Mb
    L        = model.L
    rho      = self.rho
    q_fric   = self.q_fric

    alpha_crit = project( (q_geo + q_fric) / (Mb*L*rho), annotate=False)
    model.init_alpha_crit(alpha_crit, cls=self)

  def solve_basal_melt_rate(self):
    """
    Solve for the basal melt rate stored in model.Mb.
    """ 
    # calculate melt-rate : 
    s = "::: solving for basal-melt rate :::"
    print_text(s, cls=self)
    
    model    = self.model
    B        = model.B
    T        = model.T
    T_melt   = model.T_melt
    L        = model.L
    q_geo    = model.q_geo
    rho      = self.rho
    k        = self.k
    q_fric   = self.q_fric

    gradB = as_vector([B.dx(0), B.dx(1), -1])
    dTdn  = k * dot(grad(T), gradB)
    nMb   = project((q_geo + q_fric - dTdn) / (L*rho), model.Q,
                    annotate=False)
    nMb_v    = nMb.vector().array()
    T_melt_v = T_melt.vector().array()
    T_v      = T.vector().array()
    nMb_v[T_v < T_melt_v] = 0.0    # if frozen, no melt
    nMb_v[model.shf_dofs] = 0.0    # does apply over floating regions
    model.assign_variable(model.Mb, nMb_v, cls=self)

  def calc_bulk_density(self):
    """
    Calculate the bulk density stored in model.rho_b.
    """
    # calculate bulk density :
    s = "::: calculating bulk density :::"
    print_text(s, cls=self)
    model       = self.model
    rho_b       = project(self.rho, annotate=False)
    model.assign_variable(model.rhob, rho_b, cls=self)


class EnergyHybrid(Energy):
  """
  New 2D hybrid model.
  """
  def initialize(self, model, solve_params=None, transient=False,
                 use_lat_bc=False, epsdot_ftn=None):
    """ 
    Set up energy equation residual. 
    """
    s    = "::: INITIALIZING HYBRID ENERGY PHYSICS :::"
    print_text(s, cls=self)

    if type(model) != D2Model:
      s = ">>> EnergyHybrid REQUIRES A 'D2Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)
    
    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    self.transient = transient

    # CONSTANTS
    year    = model.spy
    g       = model.g
    n       = model.n
            
    k       = model.ki
    rho     = model.rhoi
    Cp      = model.ci
    kappa   = year*k/(rho*Cp)
            
    q_geo   = model.q_geo
    S       = model.S
    B       = model.B
    beta    = model.beta
    T_s     = model.T_surface
    T_w     = model.T_w
    U       = model.UHV
    H       = model.H
    H0      = model.H0
    T_      = model.T_
    T0_     = model.T0_
    deltax  = model.deltax
    sigmas  = model.sigmas
    eps_reg = model.eps_reg
    h       = model.h
    dt      = model.time_step
    N_T     = model.N_T
    
    Bc      = 3.61e-13*year
    Bw      = 1.73e3*year  # model.a0 ice hardness
    Qc      = 6e4
    Qw      = model.Q0     # ice act. energy
    Rc      = model.R      # gas constant
    gamma   = model.gamma  # pressure melting point depth dependence
   
    # get velocity components : 
    # ANSATZ    
    coef  = [lambda s:1.0, lambda s:1./4.*(5*s**4 - 1.0)]
    dcoef = [lambda s:0.0, lambda s:5*s**3]
    
    u_   = [U[0], U[2]]
    v_   = [U[1], U[3]]
    
    u    = VerticalBasis(u_, coef, dcoef)
    v    = VerticalBasis(v_, coef, dcoef)
    
    # FUNCTION SPACES
    Q = model.Q
    Z = model.Z
    
    # ENERGY BALANCE 
    Psi = TestFunction(Z)
    dT  = TrialFunction(Z)
    
    T  = VerticalFDBasis(T_,  deltax, coef, sigmas)
    T0 = VerticalFDBasis(T0_, deltax, coef, sigmas)

    # METRICS FOR COORDINATE TRANSFORM
    def dsdx(s):
      return 1./H*(S.dx(0) - s*H.dx(0))
    
    def dsdy(s):
      return 1./H*(S.dx(1) - s*H.dx(1))
    
    def dsdz(s):
      return -1./H
    
    def epsilon_dot(s):
      return ( + (u.dx(s,0) + u.ds(s)*dsdx(s))**2 \
               + (v.dx(s,1) + v.ds(s)*dsdy(s))**2 \
               + (u.dx(s,0) + u.ds(s)*dsdx(s))*(v.dx(s,1) + v.ds(s)*dsdy(s)) \
               + 0.25*((u.ds(s)*dsdz(s))**2 + (v.ds(s)*dsdz(s))**2 \
               + (+ (u.dx(s,1) + u.ds(s)*dsdy(s)) \
                  + (v.dx(s,0) + v.ds(s)*dsdx(s)))**2) \
               + eps_reg)
    
    def A_v(T):
      return conditional(le(T,263.15),Bc*exp(-Qc/(Rc*T)),Bw*exp(-Qw/(Rc*T)))
    
    def eta_v(s):
      return A_v(T0.eval(s))**(-1./n)/2.*epsilon_dot(s)**((1.-n)/(2*n))
    
    def w(s):
      w_0 = (U[0].dx(0) + U[1].dx(1))*(s-1.)
      w_2 = + (U[2].dx(0) + U[3].dx(1))*(s**(n+2) - s)/(n+1) \
            + (n+2)/H*U[2]*(1./(n+1)*(s**(n+1) - 1.)*S.dx(0) \
            - 1./(n+1)*(s**(n+2) - 1.)*H.dx(0)) \
            + (n+2)/H*U[3]*(+ 1./(n+1)*(s**(n+1) - 1.)*S.dx(1) \
                            - 1./(n+1)*(s**(n+2) - 1.)*H.dx(1))
      return (u(1)*B.dx(0) + v(1)*B.dx(1)) - 1./dsdz(s)*(w_0 + w_2) 
    
    R_T = 0

    for i in range(N_T):
      # SIGMA COORDINATE
      s = i/(N_T-1.0)
    
      # EFFECTIVE VERTICAL VELOCITY
      w_eff = u(s)*dsdx(s) + v(s)*dsdy(s) + w(s)*dsdz(s)

      if transient:
        w_eff += 1.0/H*(1.0 - s)*(H - H0)/dt
    
      # STRAIN HEAT
      #Phi_strain = (2*n)/(n+1)*2*eta_v(s)*epsilon_dot(s)
      Phi_strain = 4*eta_v(s)*epsilon_dot(s)
    
      # STABILIZATION SCHEME
      #Umag   = sqrt(u(s)**2 + v(s)**2 + 1e-3)
      #tau    = h/(2*Umag)
      #Psihat = Psi[i] + tau*(u(s)*Psi[i].dx(0) + v(s)*Psi[i].dx(1))
      Unorm  = sqrt(u(s)**2 + v(s)**2 + DOLFIN_EPS)
      PE     = Unorm*h/(2*kappa)
      tau    = 1/tanh(PE) - 1/PE
      Psihat = Psi[i] + h*tau/(2*Unorm) * (+ u(s)*Psi[i].dx(0) \
                                           + v(s)*Psi[i].dx(1) )
      
      # SURFACE BOUNDARY
      if i==0:
        R_T += Psi[i]*(T(i) - T_s)*dx
      # BASAL BOUNDARY
      elif i==(N_T-1):
        R_T += (u(s)*T.dx(i,0) + v(s)*T.dx(i,1))*Psihat*dx
        R_T += -Phi_strain/(rho*Cp)*Psi[i]*dx 
        R_T += -w_eff*q_geo/(rho*Cp*kappa*dsdz(s))*Psi[i]*dx
        f    = (q_geo + beta*(u(s)**2 + v(s)**2))/(rho*Cp*kappa*dsdz(s))
        R_T += -2.*kappa*dsdz(s)**2*(+ (T(N_T-2) - T(N_T-1)) / deltax**2 \
                                     - f/deltax)*Psi[i]*dx
      # INTERIOR
      else:
        R_T += -kappa*dsdz(s)**2.*T.d2s(i)*Psi[i]*dx
        R_T += w_eff*T.ds(i)*Psi[i]*dx
        R_T += (u(s)*T.dx(i,0) + v(s)*T.dx(i,1))*Psihat*dx
        R_T += -Phi_strain/(rho*Cp)*Psi[i]*dx 
   
      if transient: 
        dTdt = (T(i) - T0(i))/dt
        R_T += dTdt*Psi[i]*dx
    
    # PRETEND THIS IS LINEAR (A GOOD APPROXIMATION IN THE TRANSIENT CASE)
    self.R_T = replace(R_T, {T_:dT})

    # pressure melting point calculation, do not annotate for initial calc :
    self.Tm  = as_vector([T_w - sigma*gamma*rho*g*H for sigma in sigmas])
    self.calc_T_melt(annotate=False)

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params

  def default_ffc_options(self):
    """ 
    Returns a set of default ffc options that yield good performance
    """
    ffc_options = {"optimize"               : True,
                   "eliminate_zeros"        : True,
                   "precompute_basis_const" : True,
                   "precompute_ip_const"    : True}
    return ffc_options

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    m_params  = {'solver'      : {'linear_solver': 'mumps'},
                 'ffc_params'  : self.default_ffc_options()}
    return m_params

  def solve(self, annotate=True):
    """
    Solves for hybrid energy.
    """
    s    = "::: solving 'EnergyHybrid' for temperature :::"
    print_text(s, cls=self)
    
    model  = self.model

    # SOLVE TEMPERATURE
    solve(lhs(self.R_T) == rhs(self.R_T), model.T_,
          solver_parameters=self.solve_params['solver'],
          form_compiler_parameters=self.solve_params['ffc_params'],
          annotate=annotate)
    print_min_max(model.T_, 'T_', cls=self)

    if self.transient:
      model.T0_.assign(model.T_)

    #  correct for pressure melting point :
    T_v                 = model.T_.vector().array()
    T_melt_v            = model.Tm.vector().array()
    T_v[T_v > T_melt_v] = T_melt_v[T_v > T_melt_v]
    model.assign_variable(model.T_, T_v, cls=self)
    
    out_T = model.T_.split(True)            # deepcopy avoids projections
    
    model.assign_variable(model.Ts, out_T[0],  cls=self)
    model.assign_variable(model.Tb, out_T[-1], cls=self) 

  def calc_T_melt(self, annotate=True):
    """
    Calculates pressure-melting point in model.T_melt.
    """
    s    = "::: calculating pressure-melting temperature :::"
    print_text(s, cls=self)

    model   = self.model
    
    T_melt  = project(self.Tm, annotate=annotate)
    
    Tb_m    = T_melt.split(True)[-1]  # deepcopy avoids projections
    model.assign_variable(model.T_melt, Tb_m,   cls=self)
    model.assign_variable(model.Tm,     T_melt, cls=self)
    
  def solve_basal_melt_rate(self):
    """
    Solve for the basal melt rate stored in model.Mb.
    """ 
    # FIXME: need to form an expression for dT/dz
    s = "::: calculating basal melt-rate :::"
    print_text(s, cls=self)
    
    model  = self.model
    B      = model.B
    rhoi   = model.rhoi
    T      = model.Tb
    L      = model.L
    ki     = model.ki
    q_geo  = model.q_geo
    beta   = model.beta
    u_b    = model.u_b
    v_b    = model.v_b
    w_b    = model.w_b
    q_fric = beta * (u_b**2 + v_b**2 + w_b**2)
    
    gradB = as_vector([B.dx(0), B.dx(1), -1])
    gradT = as_vector([T.dx(0), T.dx(1), 0.0])
    dHdn  = k * dot(gradT, gradB)
    nMb   = project((q_geo + q_fric - dHdn) / (L*rhoi), model.Q,
                    annotate=False)
    nMb_v = nMb.vector().array()
    #nMb_v[nMb_v < 0.0]  = 0.0
    #nMb_v[nMb_v > 10.0] = 10.0
    model.assign_variable(model.Mb, nMb_v, cls=self)


class EnergyFirn(Energy):

  def __init__(self, model, solve_params=None):
    """
    """
    s    = "::: INITIALIZING FIRN ENERGY PHYSICS :::"
    print_text(s, cls=self)

    if type(model) != D1Model:
      s = ">>> FirnEnergy REQUIRES A 'D1Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)
    
    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    mesh    = model.mesh
    Q       = model.Q

    spy     = model.spy
    theta   = model.theta                     # enthalpy
    theta0  = model.theta0                    # previous enthalpy
    T       = model.T                         # temperature
    rhof    = model.rho                       # density of firn
    sigma   = model.sigma                     # overburden stress
    r       = model.r                         # grain size
    w       = model.w                         # velocity
    m       = model.m                         # mesh velocity
    dt      = model.time_step                 # timestep
    rhoi    = model.rhoi                      # density of ice
    rhow    = model.rhow                      # density of water 
    ci      = model.ci                        # heat capacity of ice
    cw      = model.cw                        # heat capacity of water
    kw      = model.kw                        # thermal conductivity of water
    T       = model.T
    T_w     = model.T_w
    L       = model.L
    thetasp = model.thetasp
    p       = model.p
    etaw    = model.etaw
    rhow    = model.rhow
    #w       = w - m
    z       = model.x[0]
    g       = model.g
    S       = model.S
    h       = model.h
    #W       = model.W
    dx      = model.dx
    
    xi      = TestFunction(Q)
    dtheta  = TrialFunction(Q)
    
    # thermal conductivity parameter :
    #ki  = model.ki*(rho / rhoi)**2
    ki  = 9.828 * exp(-0.0057*T)
    ci  = 152.5 + 7.122*T
    
    # water content :
    Wm    = conditional(lt(theta, ci*T_w), 0.0, (theta - ci*T_w) / L)

    # bulk properties :
    kb   = kw * Wm   + (1-Wm)*ki
    cb   = cw * Wm   + (1-Wm)*ci
    rhob = rhow * Wm + (1-Wm)*rhof

    # initialize energy :
    T_v = T.vector().array()
    c_v = 152.5 + 7.122*T_v
    model.assign_variable(theta,  c_v*T_v)
    model.assign_variable(theta0, c_v*T_v)
    
    # initialize heat capacity : 
    model.assign_variable(model.cif, project(ci, annotate=False))
   
    # boundary condition on the surface : 
    self.thetaBc = DirichletBC(Q, model.theta_surface,  model.surface)
   
    # Darcy flux :
    k     = 0.077 * r**2 * exp(-7.8*rhob/rhow) # intrinsic permeability
    phi   = 1 - rhob/rhoi                      # porosity
    Wmi   = 0.0057 / (1 - phi) + 0.017         # irriducible water content
    Se    = (Wm - Wmi) / (1 - Wmi)             # effective saturation
    K     = k * rhow * g / etaw                # unsaturated hydraulic cond.
    krw   = Se**3.0                            # relative permeability
    psi_m = p / (rhow * g)                     # matric potential head
    psi_g = z                                  # gravitational potential head
    psi   = psi_m + psi_g                      # total water potential head
    u     = - K * krw * psi.dx(0)              # darcy water velocity
      
    # skewed test function in areas with high velocity :
    PE     = u*h/(2*kb/(rhob*cb))
    tau    = 1/tanh(PE) - 1/PE
    xihat  = xi + h*tau/2 * xi.dx(0)
      
    # enthalpy residual :
    eta       = 1.0
    theta_mid = eta*theta + (1 - eta)*theta0
    delta     = + kb/(rhob*cb) * inner(theta_mid.dx(0), xi.dx(0)) * dx \
                + (theta - theta0)/dt * xi * dx \
                + w * theta_mid.dx(0) * xi * dx \
                + u * theta_mid.dx(0) * xi * dx \
                - sigma * w.dx(0) / rhob * xi * dx
    
    # equation to be minimzed :
    self.J     = derivative(delta, theta, dtheta)   # jacobian
    
    self.ci    = ci
    self.delta = delta
    self.u     = u
    self.Wm    = Wm
    self.Wmi   = Wmi

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    params = {'newton_solver' : {'relaxation_parameter'     : 1.0,
                                 'maximum_iterations'      : 25,
                                 'error_on_nonconvergence' : False,
                                 'relative_tolerance'      : 1e-10,
                                 'absolute_tolerance'      : 1e-10}}
    m_params  = {'solver' : params}
    return m_params

  def solve(self, annotate=True):
    """
    """
    s    = "::: solving FirnEnergy :::"
    print_text(s, cls=self)
    
    model = self.model

    # newton's iterative method :
    solve(self.delta == 0, model.theta, self.thetaBc, J=self.J, 
          solver_parameters=self.solve_params['solver'],
          annotate=annotate)

    model.assign_variable(model.W0,  model.W)
    model.assign_variable(model.W,   project(self.Wm, annotate=False))
    model.assign_variable(model.cif, project(self.ci, annotate=False))
    
    T_w     = model.T_w(0)
    rhow    = model.rhow(0)
    rhoi    = model.rhoi(0)
    g       = model.g(0)
    ci      = model.cif.vector().array()
    thetasp = ci * T_w
    L       = model.L(0)

    # update coefficients used by enthalpy :
    thetap     = model.theta.vector().array()
    thetahigh  = np.where(thetap > thetasp)[0]
    thetalow   = np.where(thetap < thetasp)[0]
    
    # calculate T :
    Tp             = thetap / ci
    Tp[thetahigh]  = T_w
    model.assign_variable(model.T, Tp)

    # calculate dW :
    Wp   = model.W.vector().array()
    Wp0  = model.W0.vector().array()
    dW   = Wp - Wp0                 # water content change
    model.assign_variable(model.dW, dW)
    
    ## calculate W :
    #model.assign_variable(model.W0, model.W)
    #Wp             = model.W.vector().array()
    #Wp[thetahigh]  = (thetap[thetahigh] - ci*T_w) / L
    #Wp[thetalow]   = 0.0
    #Wp0            = model.W0.vector().array()
    #dW             = Wp - Wp0                 # water content change
    #model.assign_variable(model.W,  Wp)
    #model.assign_variable(model.dW, dW)

    print_min_max(model.T,     'T')
    print_min_max(model.theta, 'theta')
    print_min_max(model.W,     'W')

    p     = model.vert_integrate(rhow * g * model.W)
    phi   = 1 - model.rho/rhoi                         # porosity
    Wmi   = 0.0057 / (1 - phi) + 0.017                 # irr. water content
    model.assign_variable(model.p,   p)
    model.assign_variable(model.u,   project(self.u, annotate=False))
    model.assign_variable(model.Smi, project(Wmi, annotate=False))
    print_min_max(model.p, 'p')
    print_min_max(model.u, 'u')


 
