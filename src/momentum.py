from fenics         import *
from dolfin_adjoint import *
from io             import print_text, print_min_max
from D3Model        import D3Model
from physics_new    import Physics
import sys


class Momentum(Physics):
  """
  Abstract class outlines the structure of a momentum calculation.
  """
  
  def color(self):
    """
    return the default color for this class.
    """
    return 'cyan'

  def get_residual(self):
    """
    Returns the momentum residual.
    """
    raiseNotDefined()

  def get_U(self):
    """
    Return the velocity Function.
    """
    raiseNotDefined()
  
  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    nparams = {'newton_solver' : {'linear_solver'            : 'cg',
                                  'preconditioner'           : 'hypre_amg',
                                  'relative_tolerance'       : 1e-8,
                                  'relaxation_parameter'     : 1.0,
                                  'maximum_iterations'       : 25,
                                  'error_on_nonconvergence'  : False}}
    m_params  = {'solver' : nparams}
    return m_params
  
  def solve(self, annotate=True, params=None):
    """ 
    Perform the Newton solve of the momentum equations 
    """
    raiseNotDefined()


class MomentumStokes(Momentum):
  """  
  """
  def __init__(self, model, solve_params=None,
               linear=False, use_lat_bcs=False, use_pressure_bc=True):
    """ 
    Here we set up the problem, and do all of the differentiation and
    memory allocation type stuff.
    """
    s = "::: INITIALIZING FULL-STOKES PHYSICS :::"
    print_text(s, self.color())
    
    if type(model) != D3Model:
      s = ">>> MomentumStokes REQUIRES A 'D3Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)

    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    self.model  = model
    
    # momenturm and adjoint :
    G      = Function(model.MV, name = 'G')
    dU     = TrialFunction(model.MV)
    Tst    = TestFunction(model.MV)
    Lam    = Function(model.MV)
   
    # function assigner goes from the U function solve to U3 vector 
    # function used to save :
    self.assx  = FunctionAssigner(model.V.sub(0), model.Q)
    self.assy  = FunctionAssigner(model.V.sub(1), model.Q)
    self.assz  = FunctionAssigner(model.V.sub(2), model.Q)
    self.assp  = FunctionAssigner(model.Q,        model.MV.sub(1))

    mesh       = model.mesh
    r          = model.r
    S          = model.S
    B          = model.B
    H          = S - B
    z          = model.x[2]
    W          = model.W
    R          = model.R
    rhoi       = model.rhoi
    rhow       = model.rhow
    g          = model.g
    beta       = model.beta
    h          = model.h
    N          = model.N
    D          = model.D

    gradS      = grad(S)
    gradB      = grad(B)
    
    dx_s       = model.dx_s
    dx_g       = model.dx_g
    dx         = model.dx
    dGnd       = model.dGnd
    dFlt       = model.dFlt
    dSde       = model.dSde
    dBed       = model.dBed
     
    # new constants :
    p0         = 101325
    T0         = 288.15
    M          = 0.0289644
    ci         = model.ci
    
    #===========================================================================
    # define variational problem :
    du,  dp = split(dU)
    U,   p  = split(G)
    Phi, xi = split(Tst)

    u,   v,   w   = U
    phi, psi, chi = Phi
   
    # form the viscosity : 
    if linear:
      s   = "    - using linear form of momentum using model.U3 in epsdot -"
      print_text(s, self.color())
      epsdot = self.effective_strain_rate(model.U3.copy(True))
    else:
      s   = "    - using nonlinear form of momentum -"
      print_text(s, self.color())
      epsdot   = self.effective_strain_rate(U)
    
    eps_reg    = model.eps_reg
    n          = model.n
    b_shf      = model.b_shf
    b_gnd      = model.b_gnd
    
    eta_shf    = 0.5 * b_shf * (epsdot + eps_reg)**((1-n)/(2*n))
    eta_gnd    = 0.5 * b_gnd * (epsdot + eps_reg)**((1-n)/(2*n))
    
    # gravity vector :
    gv   = as_vector([0, 0, -g])
    f_w  = rhoi*g*(S - z) + rhow*g*D
    I    = Identity(3)

    epi       = self.strain_rate_tensor(U)
    tau_shf   = 2*eta_shf*epi
    tau_gnd   = 2*eta_gnd*epi
    sigma_shf = tau_shf - p*I
    sigma_gnd = tau_gnd - p*I
    tau_n     = dot(N, dot(tau_gnd, N))
    
    # conservation of momentum :
    R1 = + inner(sigma_shf, grad(Phi)) * dx_s \
         + inner(sigma_gnd, grad(Phi)) * dx_g \
         - rhoi * dot(gv, Phi) * dx \
         + beta**2 * u * phi * dGnd \
         + beta**2 * v * psi * dGnd \
         + beta**2 * w * chi * dGnd \
         - (2*eta_gnd*u.dx(0) - tau_n)*N[0] * phi * dGnd \
         - eta_gnd*(u.dx(1) + v.dx(0))*N[1] * phi * dGnd \
         - eta_gnd*(u.dx(2) + w.dx(0))*N[2] * phi * dGnd \
         - eta_gnd*(u.dx(1) + v.dx(0))*N[0] * psi * dGnd \
         - (2*eta_gnd*v.dx(1) - tau_n)*N[1] * psi * dGnd \
         - eta_gnd*(v.dx(2) + w.dx(1))*N[2] * psi * dGnd \
         #- f_w * dot(N, Phi) * dFlt \
         #- dot(dot(N, dot(tau_gnd, N)) * N, Phi) * dGnd \
         #- p_a * dot(N, Phi) * dSrf \
         #+ beta**2 * dot(U, Phi) * dGnd \
    
    if (not model.use_periodic_boundaries 
        and not use_lat_bcs and use_pressure_bc):
      s = "    - using cliff-pressure boundary condition -"
      print_text(s, self.color())
      R1 -= f_w * dot(N, Phi) * dSde \
     
    # conservation of mass :
    R2 = + div(U)*xi*dx \
         #+ beta**2*(u*B.dx(0) + v*B.dx(1))*chi*dGnd \
         #+ dot(U, N)*xi*dBed
    
    # total residual :
    self.mom_F = R1 + R2
    
    self.mom_Jac = derivative(self.mom_F, G, dU)
   
    self.mom_bcs = []
      
    # add lateral boundary conditions :  
    if use_lat_bcs:
      s = "    - using lateral boundary conditions -"
      print_text(s, self.color())

      ff = model.ff
      MV = model.MV

      self.mom_bcs.append(DirichletBC(MV.sub(0).sub(0), model.u_lat, ff, 7))
      self.mom_bcs.append(DirichletBC(MV.sub(0).sub(1), model.v_lat, ff, 7))
      self.mom_bcs.append(DirichletBC(MV.sub(0).sub(2), model.w_lat, ff, 7))

    #self.mom_bcs.append(DirichletBC(model.MV.sub(0), 
    #                                Constant((0,0,0)), model.ff, 
    #                                model.GAMMA_B_GND))
    
    self.G       = G
    self.U       = U 
    self.p       = p
    self.dU      = dU
    self.Tst     = Tst
    self.Lam     = Lam
    self.epsdot  = epsdot
    self.eta_shf = eta_shf
    self.eta_gnd = eta_gnd
  
  def get_residual(self):
    """
    Returns the momentum residual.
    """
    return self.mom_F

  def get_U(self):
    """
    Return the velocity Function.
    """
    return self.U

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params
  
  def strain_rate_tensor(self, U):
    """
    return the strain-rate tensor of <U>.
    """
    return 0.5 * (grad(U) + grad(U).T)

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

  def stress_tensor(self):
    """
    return the BP Cauchy stress tensor.
    """
    # FIXME: needs eta
    s   = "::: forming the Cauchy stress tensor :::"
    print_text(s, self.color())
    epi   = self.strain_rate_tensor(self.U)
    I     = Identity(3)

    sigma = 2*self.eta*epi - self.p*I
    return sigma

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    nparams = {'newton_solver' : {'linear_solver'            : 'mumps',
                                  'relative_tolerance'       : 1e-8,
                                  'relaxation_parameter'     : 1.0,
                                  'maximum_iterations'       : 25,
                                  'error_on_nonconvergence'  : False}}
    m_params  = {'solver'      : nparams}
    return m_params

  def solve(self, annotate=True):
    """ 
    Perform the Newton solve of the full-Stokes equations 
    """
    model  = self.model
    params = self.solve_params
    
    # solve nonlinear system :
    rtol   = params['solver']['newton_solver']['relative_tolerance']
    maxit  = params['solver']['newton_solver']['maximum_iterations']
    alpha  = params['solver']['newton_solver']['relaxation_parameter']
    s      = "::: solving BP horizontal velocity with %i max iterations" + \
             " and step size = %.1f :::"
    print_text(s % (maxit, alpha), self.color())
    
    # compute solution :
    solve(self.mom_F == 0, self.G, J = self.mom_Jac, bcs = self.mom_bcs,
          annotate = annotate, solver_parameters = params['solver'])
    U, p = self.G.split()
    u, v, w = split(U)

    self.assx.assign(model.u, project(u, model.Q, annotate=False))
    self.assy.assign(model.v, project(v, model.Q, annotate=False))
    self.assz.assign(model.w, project(w, model.Q, annotate=False))
    self.assp.assign(model.p, p)

    print_min_max(model.U3, 'U')
    print_min_max(model.p,  'p')


class MomentumDukowiczStokesReduced(Momentum):
  """  
  """
  def __init__(self, model, solve_params=None,
               linear=False, use_lat_bcs=False, use_pressure_bc=True):
    """ 
    Here we set up the problem, and do all of the differentiation and
    memory allocation type stuff.
    """
    s = "::: INITIALIZING DUKOWICZ REDUCED FULL-STOKES PHYSICS :::"
    print_text(s, self.color())
    
    if type(model) != D3Model:
      s = ">>> MomentumStokes REQUIRES A 'D3Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)

    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    self.model  = model
    
    # momenturm and adjoint :
    U      = Function(model.Q2, name = 'G')
    dU     = TrialFunction(model.Q2)
    Phi    = TestFunction(model.Q2)
    Lam    = Function(model.Q2)
   
    # function assigner goes from the U function solve to U3 vector 
    # function used to save :
    self.assx  = FunctionAssigner(model.V.sub(0), model.Q2.sub(0))
    self.assy  = FunctionAssigner(model.V.sub(1), model.Q2.sub(1))
    self.assz  = FunctionAssigner(model.V.sub(2), model.Q)

    mesh       = model.mesh
    r          = model.r
    S          = model.S
    B          = model.B
    H          = S - B
    z          = model.x[2]
    W          = model.W
    R          = model.R
    rhoi       = model.rhoi
    rhow       = model.rhow
    g          = model.g
    beta       = model.beta
    h          = model.h
    N          = model.N
    D          = model.D

    gradS      = grad(S)
    gradB      = grad(B)
    
    dx_s       = model.dx_s
    dx_g       = model.dx_g
    dx         = model.dx
    dGnd       = model.dGnd
    dFlt       = model.dFlt
    dSde       = model.dSde
    dBed       = model.dBed
     
    # new constants :
    p0         = 101325
    T0         = 288.15
    M          = 0.0289644
    ci         = model.ci
    
    #===========================================================================
    # define variational problem :
    phi, psi = Phi
    du,  dv  = dU
    u,   v   = U

    w = u*B.dx(0) + v*B.dx(1) - (u.dx(0) + v.dx(1))*(z - B)
   
    # form the viscosity : 
    if linear:
      s   = "    - using linear form of momentum using model.U3 in epsdot -"
      print_text(s, self.color())
      epsdot = self.effective_strain_rate(model.U3.copy(True))
    else:
      s   = "    - using nonlinear form of momentum -"
      print_text(s, self.color())
      epsdot   = self.effective_strain_rate(as_vector([u,v,w]))
    
    eps_reg    = model.eps_reg
    n          = model.n
    b_shf      = model.b_shf
    b_gnd      = model.b_gnd
    
    # 1) Viscous dissipation
    Vd_shf  = (2*n)/(n+1) * b_shf * (epsdot + eps_reg)**((n+1)/(2*n))
    Vd_gnd  = (2*n)/(n+1) * b_gnd * (epsdot + eps_reg)**((n+1)/(2*n))
      
    # 2) Potential energy
    Pe     = rhoi * g * (u*S.dx(0) + v*S.dx(1))

    # 3) Dissipation by sliding
    wn = u*B.dx(0) + v*B.dx(1)
    Sl_gnd = 0.5 * beta**2 * H**r * (u**2 + v**2 + w**2)
    Sl_shf = 0.5 * Constant(1e-2) * (u**2 + v**2 + w**2)

    # 4) pressure boundary
    Pb     = - (rhoi*g*(S - z) + rhow*g*D) * (u*N[0] + v*N[1] + w*N[2]) 

    # Variational principle
    A      = Vd_shf*dx_s + Vd_gnd*dx_g + Pe*dx + Sl_gnd*dGnd + Sl_shf*dFlt
    
    if (not model.use_periodic_boundaries 
        and not use_lat_bcs and use_pressure_bc):
      s = "    - using cliff-pressure boundary condition -"
      print_text(s, self.color())
      A += Pb*dSde

    # Calculate the first variation (the action) of the variational 
    # principle in the direction of the test function
    self.mom_F = derivative(A, U, Phi)

    # Calculate the first variation of the action (the Jacobian) in
    # the direction of a small perturbation in U
    self.mom_Jac = derivative(self.mom_F, U, dU)
    
    self.mom_bcs = []
      
    # add lateral boundary conditions :  
    if use_lat_bcs:
      s = "    - using lateral boundary conditions -"
      print_text(s, self.color())

      self.mom_bcs.append(DirichletBC(Q2.sub(0), model.u_lat, model.ff, 4))
      self.mom_bcs.append(DirichletBC(Q2.sub(1), model.v_lat, model.ff, 4))
    
    # keep the residual for adjoint solves :
    self.A       = A
    self.U       = U 
    self.w       = w
    self.dU      = dU
    self.Phi     = Phi
    self.Lam     = Lam
    self.epsdot  = epsdot
  
  def get_residual(self):
    """
    Returns the momentum residual.
    """
    return self.A

  def get_U(self):
    """
    Return the velocity Function.
    """
    return self.U

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params
  
  def strain_rate_tensor(self, U):
    """
    return the strain-rate tensor of <U>.
    """
    u,v,w  = U
    epi    = 0.5 * (grad(U) + grad(U).T)
    epi22  = -u.dx(0) - v.dx(1)          # incompressibility
    epsdot = as_matrix([[epi[0,0],  epi[0,1],  epi[0,2]],
                        [epi[1,0],  epi[1,1],  epi[1,2]],
                        [epi[2,0],  epi[2,1],  epi22]])
    return epsdot

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
    #u,v,w = U
    #epsdot = 0.5 * (+ (u.dx(0))**2 + (v.dx(1))**2 + (u.dx(0) + v.dx(1))**2 \
    #                + 0.5*(u.dx(1) + v.dx(0))**2 \
    #                + 0.5*((u.dx(2) + w.dx(0))**2 + (v.dx(2) + w.dx(1))**2))
    return epsdot

  def stress_tensor(self):
    """
    return the BP Cauchy stress tensor.
    """
    # FIXME: needs eta
    s   = "::: forming the Cauchy stress tensor :::"
    print_text(s, self.color())
    U     = as_vector([self.U[0], self.U[1], self.U[2]])
    epi   = self.strain_rate_tensor(U)
    I     = Identity(3)

    sigma = 2*self.eta*epi - self.U[3]*I
    return sigma

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    nparams = {'newton_solver' : {'linear_solver'            : 'cg',
                                  'preconditioner'           : 'hypre_amg',
                                  'relative_tolerance'       : 1e-8,
                                  'relaxation_parameter'     : 1.0,
                                  'maximum_iterations'       : 25,
                                  'error_on_nonconvergence'  : False}}
    m_params  = {'solver'      : nparams}
    return m_params

  def solve(self, annotate=True):
    """ 
    Perform the Newton solve of the full-Stokes equations 
    """
    model  = self.model
    params = self.solve_params
    
    # solve nonlinear system :
    rtol   = params['solver']['newton_solver']['relative_tolerance']
    maxit  = params['solver']['newton_solver']['maximum_iterations']
    alpha  = params['solver']['newton_solver']['relaxation_parameter']
    s    = "::: solving Dukowicz full-Stokes reduced equations with %i max" + \
             " iterations and step size = %.1f :::"
    print_text(s % (maxit, alpha), self.color())
    
    # compute solution :
    solve(self.mom_F == 0, self.U, J = self.mom_Jac, bcs = self.mom_bcs,
          annotate = annotate, solver_parameters = params['solver'])
    u, v = self.U.split()
    
    self.assx.assign(model.u, u)
    self.assy.assign(model.v, v)

    # solve for the vertical velocity :
    s    = "::: solving Dukowicz reduced vertical velocity :::"
    print_text(s, self.color())
    w = project(self.w, model.Q)

    self.assz.assign(model.w, w)
    
    U3 = model.U3.split(True)

    print_min_max(U3[0], 'u')
    print_min_max(U3[1], 'v')
    print_min_max(U3[2], 'w')
  
  def form_obj_ftn(self, kind='log', integral=2, g1=0.01, g2=1000):
    """
    Forms and returns an objective functional for use with adjoint.
    Saves to self.J.
    """
    self.obj_ftn_type = kind   # need to save this for printing values.
    
    model    = self.model

    dGamma   = model.ds(integral)
    u_ob     = model.u_ob
    v_ob     = model.v_ob
    adot     = model.adot
    S        = model.S
    U        = self.U

    if kind == 'log':
      J   = 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                      / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma 
      s   = "::: forming log objective function :::"
    
    elif kind == 'kinematic':
      J   = 0.5 * (+ U[0]*S.dx(0) + U[1]*S.dx(1) - (U[2] + adot))**2 * dGamma
      s   = "::: getting kinematic objective function :::"

    elif kind == 'linear':
      J   = 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      s   = "::: getting linear objective function :::"
    
    elif kind == 'log_lin_hybrid':
      J1  = g1 * 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      J2  = g2 * 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                           / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma
      self.J1  = 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      self.J2  = 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                           / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma
      J   = J1  + J2
      s   = "::: getting log/linear hybrid objective with gamma_1 = " \
            "%.1e and gamma_2 = %.1e :::" % (g1, g2)

    else:
      s = ">>> ADJOINT OBJECTION FUNCTION MAY BE 'linear', " + \
          "'log', 'kinematic', OR 'log_lin_hybrid' <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    print_text(s, self.color())
    self.J = J
    return J

  def form_reg_ftn(self, c, kind='Tikhonov', integral=2, alpha=1.0):
    """
    Forms and returns regularization functional for used with adjoint, saved to 
    self.Reg.
    """
    self.alpha = alpha   # need to save this for printing values.

    dR = self.model.ds(integral)
    
    # form regularization term 'R' :
    if kind != 'TV' and kind != 'Tikhonov':
      s    =   ">>> VALID REGULARIZATIONS ARE 'TV' AND 'Tikhonov' <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    elif kind == 'TV':
      R  = alpha * 0.5 * sqrt(inner(grad(c), grad(c)) + DOLFIN_EPS) * dR
    elif kind == 'Tikhonov':
      R  = alpha * 0.5 * inner(grad(c), grad(c)) * dR
    s   = "::: forming %s regularization with parameter alpha = %.2E :::"
    print_text(s % (kind, alpha), self.color())
    self.Reg = R
    return R


class MomentumDukowiczStokes(Momentum):
  """  
  """
  def __init__(self, model, solve_params=None,
               linear=False, use_lat_bcs=False, use_pressure_bc=True):
    """ 
    Here we set up the problem, and do all of the differentiation and
    memory allocation type stuff.
    """
    s = "::: INITIALIZING DUKOWICZ FULL-STOKES PHYSICS :::"
    print_text(s, self.color())
    
    if type(model) != D3Model:
      s = ">>> MomentumStokes REQUIRES A 'D3Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)

    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    self.model  = model
    
    # momenturm and adjoint :
    U      = Function(model.Q4, name = 'G')
    dU     = TrialFunction(model.Q4)
    Phi    = TestFunction(model.Q4)
    Lam    = Function(model.Q4)
   
    # function assigner goes from the U function solve to U3 vector 
    # function used to save :
    self.assx  = FunctionAssigner(model.V.sub(0), model.Q4.sub(0))
    self.assy  = FunctionAssigner(model.V.sub(1), model.Q4.sub(1))
    self.assz  = FunctionAssigner(model.V.sub(2), model.Q4.sub(2))
    self.assp  = FunctionAssigner(model.Q,        model.Q4.sub(3))

    mesh       = model.mesh
    r          = model.r
    S          = model.S
    B          = model.B
    H          = S - B
    z          = model.x[2]
    W          = model.W
    R          = model.R
    rhoi       = model.rhoi
    rhow       = model.rhow
    g          = model.g
    beta       = model.beta
    h          = model.h
    N          = model.N
    D          = model.D

    gradS      = grad(S)
    gradB      = grad(B)
    
    dx_s       = model.dx_s
    dx_g       = model.dx_g
    dx         = model.dx
    dGnd       = model.dGnd
    dFlt       = model.dFlt
    dSde       = model.dSde
    dBed       = model.dBed
     
    # new constants :
    p0         = 101325
    T0         = 288.15
    M          = 0.0289644
    ci         = model.ci
    
    #===========================================================================
    # define variational problem :
    phi, psi, xsi, kappa = Phi
    du,  dv,  dw,  dP    = dU
    u,   v,   w,   p     = U
   
    # form the viscosity : 
    if linear:
      s   = "    - using linear form of momentum using model.U3 in epsdot -"
      print_text(s, self.color())
      epsdot = self.effective_strain_rate(model.U3.copy(True))
    else:
      s   = "    - using nonlinear form of momentum -"
      print_text(s, self.color())
      epsdot   = self.effective_strain_rate(as_vector([u,v,w]))
    
    eps_reg    = model.eps_reg
    n          = model.n
    b_shf      = model.b_shf
    b_gnd      = model.b_gnd
    
    # 1) Viscous dissipation
    Vd_shf  = (2*n)/(n+1) * b_shf * (epsdot + eps_reg)**((n+1)/(2*n))
    Vd_gnd  = (2*n)/(n+1) * b_gnd * (epsdot + eps_reg)**((n+1)/(2*n))
      
    # 2) Potential energy
    Pe     = rhoi * g * w

    # 3) Dissipation by sliding
    Sl_gnd = 0.5 * beta**2 * H**r * (u**2 + v**2 + w**2)
    Sl_shf = 0.5 * Constant(1e-2) * (u**2 + v**2 + w**2)

    # 4) Incompressibility constraint
    Pc     = -p * (u.dx(0) + v.dx(1) + w.dx(2)) 
    
    # 5) Impenetrability constraint
    Nc     = p * (u*N[0] + v*N[1] + w*N[2])

    # 6) pressure boundary
    Pb     = - (rhoi*g*(S - z) + rhow*g*D) * (u*N[0] + v*N[1] + w*N[2]) 

    #f       = rhoi * Constant((0.0, 0.0, g))
    #tau_shf = h**2 / (12 * b_shf * rhoi**2)
    #tau_gnd = h**2 / (12 * b_gnd * rhoi**2)
    #Lsq_shf = -tau_shf * dot( (grad(p) + f), (grad(p) + f) )
    #Lsq_gnd = -tau_gnd * dot( (grad(p) + f), (grad(p) + f) )
    
    #A      = + (Vd_shf + Lsq_shf)*dx_s + (Vd_gnd + Lsq_gnd)*dx_g \
    #         + (Pe + Pc)*dx + Sl_gnd*dGnd + Sl_shf*dFlt + Nc*dBed
    
    # Variational principle
    A      = + Vd_shf*dx_s + Vd_gnd*dx_g + (Pe + Pc)*dx \
             + Sl_gnd*dGnd + Sl_shf*dFlt + Nc*dBed
    
    if (not model.use_periodic_boundaries 
        and not use_lat_bcs and use_pressure_bc):
      s = "    - using cliff-pressure boundary condition -"
      print_text(s, self.color())
      A += Pb*dSde

    # Calculate the first variation (the action) of the variational 
    # principle in the direction of the test function
    self.mom_F = derivative(A, U, Phi)

    # Calculate the first variation of the action (the Jacobian) in
    # the direction of a small perturbation in U
    self.mom_Jac = derivative(self.mom_F, U, dU)
    
    self.mom_bcs = []
      
    # add lateral boundary conditions :  
    if use_lat_bcs:
      s = "    - using lateral boundary conditions -"
      print_text(s, self.color())

      self.mom_bcs.append(DirichletBC(Q4.sub(0), model.u_lat, model.ff, 4))
      self.mom_bcs.append(DirichletBC(Q4.sub(1), model.v_lat, model.ff, 4))
      self.mom_bcs.append(DirichletBC(Q4.sub(2), model.w_lat, model.ff, 4))
    
    # keep the residual for adjoint solves :
    self.A       = A
    self.U       = U 
    self.dU      = dU
    self.Phi     = Phi
    self.Lam     = Lam
    self.epsdot  = epsdot
  
  def get_residual(self):
    """
    Returns the momentum residual.
    """
    return self.A

  def get_U(self):
    """
    Return the velocity Function.
    """
    return self.U

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params
  
  def strain_rate_tensor(self, U):
    """
    return the strain-rate tensor of <U>.
    """
    return 0.5 * (grad(U) + grad(U).T)

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

  def stress_tensor(self):
    """
    return the BP Cauchy stress tensor.
    """
    # FIXME: needs eta
    s   = "::: forming the Cauchy stress tensor :::"
    print_text(s, self.color())
    U     = as_vector([self.U[0], self.U[1], self.U[2]])
    epi   = self.strain_rate_tensor(U)
    I     = Identity(3)

    sigma = 2*self.eta*epi - self.U[3]*I
    return sigma

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    nparams = {'newton_solver' : {'linear_solver'            : 'mumps',
                                  'relative_tolerance'       : 1e-8,
                                  'relaxation_parameter'     : 1.0,
                                  'maximum_iterations'       : 25,
                                  'error_on_nonconvergence'  : False}}
    m_params  = {'solver'      : nparams}
    return m_params

  def solve(self, annotate=True):
    """ 
    Perform the Newton solve of the full-Stokes equations 
    """
    model  = self.model
    params = self.solve_params
    
    # solve nonlinear system :
    rtol   = params['solver']['newton_solver']['relative_tolerance']
    maxit  = params['solver']['newton_solver']['maximum_iterations']
    alpha  = params['solver']['newton_solver']['relaxation_parameter']
    s    = "::: solving Dukowicz full-Stokes equations with %i max" + \
             " iterations and step size = %.1f :::"
    print_text(s % (maxit, alpha), self.color())
    
    # compute solution :
    solve(self.mom_F == 0, self.U, J = self.mom_Jac, bcs = self.mom_bcs,
          annotate = annotate, solver_parameters = params['solver'])
    u, v, w, p = self.U.split()
    
    self.assx.assign(model.u, u)
    self.assy.assign(model.v, v)
    self.assz.assign(model.w, w)
    self.assp.assign(model.p, p)
    
    U3 = model.U3.split(True)

    print_min_max(U3[0], 'u')
    print_min_max(U3[1], 'v')
    print_min_max(U3[2], 'w')
    print_min_max(model.p, 'p')



class MomentumBP(Momentum):
  """				
  """
  def __init__(self, model, solve_params=None,
               linear=False, use_lat_bcs=False, use_pressure_bc=True):
    """
    Initializes the class's variables to default values that are then set
    by the individually created model.
    
    Initilize the residuals and Jacobian for the momentum equations.
    """
    s = "::: INITIALIZING BP VELOCITY PHYSICS :::"
    print_text(s, self.color())

    if type(model) != D3Model:
      s = ">>> MomentumBP REQUIRES A 'D3Model' INSTANCE, NOT %s <<<"
      print_text(s % type(model) , 'red', 1)
      sys.exit(1)
    
    if solve_params == None:
      self.solve_params = self.default_solve_params()
    else:
      self.solve_params = solve_params

    self.model  = model
    
    # momenturm and adjoint :
    U      = Function(model.Q2, name = 'U')
    wf     = Function(model.Q,  name = 'w')
    dU     = TrialFunction(model.Q2)
    Phi    = TestFunction(model.Q2)
    Lam    = Function(model.Q2)
   
    # function assigner goes from the U function solve to U3 vector 
    # function used to save :
    self.assx   = FunctionAssigner(model.V.sub(0), model.Q2.sub(0))
    self.assy   = FunctionAssigner(model.V.sub(1), model.Q2.sub(1))
    self.assz   = FunctionAssigner(model.V.sub(2), model.Q)

    mesh       = model.mesh
    r          = model.r
    V          = model.Q2
    Q          = model.Q
    S          = model.S
    B          = model.B
    H          = S - B
    z          = model.x[2]
    rhoi       = model.rhoi
    rhow       = model.rhow
    R          = model.R
    g          = model.g
    beta       = model.beta
    w          = model.w
    N          = model.N
    D          = model.D
    
    dx_s       = model.dx_s
    dx_g       = model.dx_g
    dx         = model.dx
    dGnd       = model.dGnd
    dFlt       = model.dFlt
    dSde       = model.dSde
    dBed       = model.dBed
    
    gradS      = grad(S)
    gradB      = grad(B)

    if linear:
      s   = "    - using linear form of momentum using model.U3 in epsdot -"
      print_text(s, self.color())
      epsdot = self.effective_strain_rate(model.U3.copy(True))
    else:
      s   = "    - using nonlinear form of momentum -"
      print_text(s, self.color())
      U_t      = as_vector([U[0], U[1], 0])
      epsdot   = self.effective_strain_rate(U_t)
    
    eps_reg    = model.eps_reg
    n          = model.n
    b_shf      = model.b_shf
    b_gnd      = model.b_gnd
    
    eta_shf    = 0.5 * b_shf * (epsdot + eps_reg)**((1-n)/(2*n))
    eta_gnd    = 0.5 * b_gnd * (epsdot + eps_reg)**((1-n)/(2*n))
     
    # new constants :
    p0     = 101325
    T0     = 288.15
    M      = 0.0289644
    ci     = model.ci

    dx     = model.dx
    
    #===========================================================================
    # define variational problem :

    # horizontal velocity :
    u, v      = U
    phi, psi  = Phi
    
    # vertical velocity :
    dw        = TrialFunction(Q)
    chi       = TestFunction(Q)
    
    epi_1  = as_vector([   2*u.dx(0) + v.dx(1), 
                        0.5*(u.dx(1) + v.dx(0)),
                        0.5* u.dx(2)            ])
    epi_2  = as_vector([0.5*(u.dx(1) + v.dx(0)),
                             u.dx(0) + 2*v.dx(1),
                        0.5* v.dx(2)            ])
   
    # boundary integral terms : 
    f_w    = rhoi*g*(S - z) + rhow*g*D               # lateral
    p_a    = p0 * (1 - g*z/(ci*T0))**(ci*M/R)        # surface pressure
    
    #Ne       = H + rhow/rhoi * D
    #P        = -0.383
    #Q        = -0.349
    #Unorm    = sqrt(inner(U,U) + DOLFIN_EPS)
    #Coef     = 1/(beta * Ne**(q/p))
    
    # residual :
    self.mom_F = + 2 * eta_shf * dot(epi_1, grad(phi)) * dx_s \
                 + 2 * eta_shf * dot(epi_2, grad(psi)) * dx_s \
                 + 2 * eta_gnd * dot(epi_1, grad(phi)) * dx_g \
                 + 2 * eta_gnd * dot(epi_2, grad(psi)) * dx_g \
                 + rhoi * g * gradS[0] * phi * dx \
                 + rhoi * g * gradS[1] * psi * dx \
                 + beta**2 * u * phi * dGnd \
                 + beta**2 * v * psi * dGnd \
                 - f_w * (N[0]*phi + N[1]*psi) * dFlt
                 #+ Constant(1e-2) * u * phi * dFlt \
                 #+ Constant(1e-2) * v * psi * dFlt \
    
    if (not model.use_periodic_boundaries 
        and not use_lat_bcs and use_pressure_bc):
      s = "    - using cliff-pressure boundary condition -"
      print_text(s, self.color())
      self.mom_F -= f_w * (N[0]*phi + N[1]*psi) * dSde
    
    self.w_F = + (u.dx(0) + v.dx(1) + dw.dx(2)) * chi * dx \
               + (u*N[0] + v*N[1] + dw*N[2]) * chi * dBed
  
    # Jacobian :
    self.mom_Jac = derivative(self.mom_F, U, dU)

    # list of boundary conditions
    self.mom_bcs  = []
    self.bc_w     = None
      
    # add lateral boundary conditions :  
    if use_lat_bcs:
      s = "    - using lateral boundary conditions -"
      print_text(s, self.color())

      self.mom_bcs.append(DirichletBC(V.sub(0), model.u_lat, model.ff, 7))
      self.mom_bcs.append(DirichletBC(V.sub(1), model.v_lat, model.ff, 7))
      #self.bc_w = DirichletBC(Q, model.w_lat, model.ff, 7)
    
    self.U       = U 
    self.wf      = wf
    self.dU      = dU
    self.Phi     = Phi
    self.Lam     = Lam
    self.epsdot  = epsdot
    self.eta_shf = eta_shf
    self.eta_gnd = eta_gnd
  
  def get_residual(self):
    """
    Returns the momentum residual.
    """
    return self.mom_F

  def get_U(self):
    """
    Return the velocity Function.
    """
    return self.U

  def get_solve_params(self):
    """
    Returns the solve parameters.
    """
    return self.solve_params

  def strain_rate_tensor(self, U):
    """
    return the 'Blatter-Pattyn' simplified strain-rate tensor of <U>.
    """
    u,v,w  = U
    epi    = 0.5 * (grad(U) + grad(U).T)
    epi02  = 0.5*u.dx(2)
    epi12  = 0.5*v.dx(2)
    epi22  = -u.dx(0) - v.dx(1)  # incompressibility
    epsdot = as_matrix([[epi[0,0],  epi[0,1],  epi02],
                        [epi[1,0],  epi[1,1],  epi12],
                        [epi02,     epi12,     epi22]])
    return epsdot
    
  def effective_strain_rate(self, U):
    """
    return the BP effective strain rate squared.
    """
    epi    = self.strain_rate_tensor(U)
    ep_xx  = epi[0,0]
    ep_yy  = epi[1,1]
    ep_zz  = epi[2,2]
    ep_xy  = epi[0,1]
    ep_xz  = epi[0,2]
    ep_yz  = epi[1,2]
    
    # Second invariant of the strain rate tensor squared
    epsdot = + ep_xx**2 + ep_yy**2 + ep_xx*ep_yy \
             + ep_xy**2 + ep_xz**2 + ep_yz**2
    return epsdot

  def stress_tensor(self):
    """
    return the BP Cauchy stress tensor.
    """
    s   = "::: forming the BP Cauchy stress tensor :::"
    print_text(s, self.color())
    U     = as_vector([self.U[0], self.U[1], self.wf])
    epi   = self.strain_rate_tensor(U)
    I     = Identity(3)

    sigma = 2*self.eta*epi - model.p*I
    return sigma

  def default_solve_params(self):
    """ 
    Returns a set of default solver parameters that yield good performance
    """
    nparams = {'newton_solver' : {'linear_solver'            : 'cg',
                                  'preconditioner'           : 'hypre_amg',
                                  'relative_tolerance'       : 1e-8,
                                  'relaxation_parameter'     : 1.0,
                                  'maximum_iterations'       : 25,
                                  'error_on_nonconvergence'  : False}}
    m_params  = {'solver'               : nparams,
                 'solve_vert_velocity'  : True,
                 'solve_pressure'       : True,
                 'vert_solve_method'    : 'mumps'}
    return m_params

  def solve_pressure(self):
    """
    Solve for the BP pressure 'p'.
    """
    model  = self.model
    
    # solve for vertical velocity :
    s  = "::: solving BP pressure :::"
    print_text(s, self.color())
    
    Q       = model.Q
    rhoi    = model.rhoi
    g       = model.g
    S       = model.S
    z       = model.x[2]
    p       = model.p
    eta_shf = self.eta_shf
    eta_gnd = self.eta_gnd
    w       = self.wf

    p_shf   = project(rhoi*g*(S - z) + 2*eta_shf*w.dx(2), Q, annotate=False)
    p_gnd   = project(rhoi*g*(S - z) + 2*eta_gnd*w.dx(2), Q, annotate=False)
    
    # unify the pressure over shelves and grounded ice : 
    p_v                 = p.vector().array()
    p_gnd_v             = p_gnd.vector().array()
    p_shf_v             = p_shf.vector().array()
    p_v[model.gnd_dofs] = p_gnd_v[model.gnd_dofs]
    p_v[model.shf_dofs] = p_shf_v[model.shf_dofs]
    model.assign_variable(p, p_v)
    print_min_max(p, 'p')

  def solve_vert_velocity(self):
    """ 
    Perform the Newton solve of the first order equations 
    """
    model  = self.model
    
    # solve for vertical velocity :
    s  = "::: solving BP vertical velocity :::"
    print_text(s, self.color())
    
    aw       = assemble(lhs(self.w_F))
    Lw       = assemble(rhs(self.w_F))
    if self.bc_w != None:
      self.bc_w.apply(aw, Lw)
    w_solver = LUSolver(self.solve_params['vert_solve_method'])
    w_solver.solve(aw, self.wf.vector(), Lw, annotate=False)
    #solve(lhs(self.R2) == rhs(self.R2), self.w, bcs = self.bc_w,
    #      solver_parameters = {"linear_solver" : sm})#,
    #                           "symmetric" : True},
    #                           annotate=False)
    
    self.assz.assign(model.w, self.wf)
    print_min_max(self.wf, 'w')
    
  def solve(self, annotate=True):
    """ 
    Perform the Newton solve of the first order equations 
    """

    model  = self.model
    params = self.solve_params
    
    # solve nonlinear system :
    rtol   = params['solver']['newton_solver']['relative_tolerance']
    maxit  = params['solver']['newton_solver']['maximum_iterations']
    alpha  = params['solver']['newton_solver']['relaxation_parameter']
    s      = "::: solving BP horizontal velocity with %i max iterations" + \
             " and step size = %.1f :::"
    print_text(s % (maxit, alpha), self.color())
    
    # compute solution :
    solve(self.mom_F == 0, self.U, J = self.mom_Jac, bcs = self.mom_bcs,
          annotate = annotate, solver_parameters = params['solver'])
    u, v = self.U.split()

    #self.assign_variable(model.u, u)
    #self.assign_variable(model.v, v)
    self.assx.assign(model.u, u)
    self.assy.assign(model.v, v)

    print_min_max(self.U, 'U')
      
    if params['solve_vert_velocity']:
      self.solve_vert_velocity()
    if params['solve_pressure']:
      self.solve_pressure()
  
  def form_obj_ftn(self, kind='log', integral=2, g1=0.01, g2=1000):
    """
    Forms and returns an objective functional for use with adjoint.
    Saves to self.J.
    """
    self.obj_ftn_type = kind   # need to save this for printing values.
    
    model    = self.model

    dGamma   = model.ds(integral)
    u_ob     = model.u_ob
    v_ob     = model.v_ob
    adot     = model.adot
    S        = model.S
    U        = self.U

    if kind == 'log':
      J   = 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                      / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma 
      s   = "::: forming log objective function :::"
    
    elif kind == 'kinematic':
      J   = 0.5 * (+ U[0]*S.dx(0) + U[1]*S.dx(1) - (U[2] + adot))**2 * dGamma
      s   = "::: getting kinematic objective function :::"

    elif kind == 'linear':
      J   = 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      s   = "::: getting linear objective function :::"
    
    elif kind == 'log_lin_hybrid':
      J1  = g1 * 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      J2  = g2 * 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                           / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma
      self.J1  = 0.5 * ((U[0] - u_ob)**2 + (U[1] - v_ob)**2) * dGamma
      self.J2  = 0.5 * ln(   (sqrt(U[0]**2 + U[1]**2) + 0.01) \
                           / (sqrt(u_ob**2 + v_ob**2) + 0.01))**2 * dGamma
      J   = J1  + J2
      s   = "::: getting log/linear hybrid objective with gamma_1 = " \
            "%.1e and gamma_2 = %.1e :::" % (g1, g2)

    else:
      s = ">>> ADJOINT OBJECTION FUNCTION MAY BE 'linear', " + \
          "'log', 'kinematic', OR 'log_lin_hybrid' <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    print_text(s, self.color())
    self.J = J
    return J

  def form_reg_ftn(self, c, kind='Tikhonov', integral=2, alpha=1.0):
    """
    Forms and returns regularization functional for used with adjoint, saved to 
    self.Reg.
    """
    self.alpha = alpha   # need to save this for printing values.

    dR = self.model.ds(integral)
    
    # form regularization term 'R' :
    if kind != 'TV' and kind != 'Tikhonov':
      s    =   ">>> VALID REGULARIZATIONS ARE 'TV' AND 'Tikhonov' <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    elif kind == 'TV':
      R  = alpha * 0.5 * sqrt(inner(grad(c), grad(c)) + DOLFIN_EPS) * dR
    elif kind == 'Tikhonov':
      R  = alpha * 0.5 * inner(grad(c), grad(c)) * dR
    s   = "::: forming %s regularization with parameter alpha = %.2E :::"
    print_text(s % (kind, alpha), self.color())
    self.Reg = R
    return R
 
  def print_eval_ftns(self):
    """
    Used to facilitate printing the objective function in adjoint solves.
    """
    if self.obj_ftn_type == 'log_lin_hybrid':
      J1 = assemble(self.J1)
      J2 = assemble(self.J2)
      print_min_max(J1, 'J1')
      print_min_max(J2, 'J2')
    R = assemble(self.Reg)
    J = assemble(self.J)
    print_min_max(R, 'R')
    print_min_max(J, 'J')
    
  def Lagrangian(self):
    """
    Returns the Lagrangian of the momentum equations.
    """
    s  = "::: forming Lagrangian :::"
    print_text(s, self.color())
    # this is the adjoint of the momentum residual, the Lagrangian :
    return replace(self.mom_F, {self.Phi:self.dU})

  def Hamiltonian(self, I):
    """
    Returns the Hamiltonian of the momentum equations with objective function
    <I>.
    """
    s  = "::: forming Hamiltonian :::"
    print_text(s, self.color())
    # the Hamiltonian :
    return I + self.Lagrangian()

  def dHdc(self, I, L, c): 
    """
    Returns the derivative of the Hamiltonian consisting of ajoint-computed
    self.Lam values w.r.t. the control variable <c>, i.e., 

       dH    d [                 ]
       -- = -- [ I + L(self.Lam) ]
       dc   dc [                 ]

    """
    s  = "::: forming dHdc :::"
    print_text(s, self.color())
    # we need to evaluate the Hamiltonian with the values of Lam computed from
    # self.dI in order to get the derivative of the Hamiltonian w.r.t. the 
    # control variables.  Hence we need a new Lagrangian with the trial 
    # functions replaced with the computed Lam values.
    L_lam  = replace(L, {self.dU : self.Lam})

    # the Hamiltonian with unknowns replaced with computed Lam :
    H_lam  = I + L_lam

    # the derivative of the Hamiltonian w.r.t. the control variables in the 
    # direction of a P1 test function :
    return derivative(H_lam, c, TestFunction(self.model.Q))
    
  def solve_adjoint_momentum(self, H):
    """
    Solves for the adjoint variables self.Lam from the Hamiltonian <H>.
    """
    # we desire the derivative of the Hamiltonian w.r.t. the model state U
    # in the direction of the test function Phi to vanish :
    dI = derivative(H, self.U, self.Phi)
    
    s  = "::: solving adjoint momentum :::"
    print_text(s, self.color())
    
    aw = assemble(lhs(dI))
    Lw = assemble(rhs(dI))
    
    a_solver = KrylovSolver('cg', 'hypre_amg')
    a_solver.solve(aw, self.Lam.vector(), Lw, annotate=False)

    #lam_nx, lam_ny = model.Lam.split(True)
    #lam_ix, lam_iy = model.Lam.split()

    #if self.config['adjoint']['surface_integral'] == 'shelves':
    #  lam_nx.vector()[model.gnd_dofs] = 0.0
    #  lam_ny.vector()[model.gnd_dofs] = 0.0
    #elif self.config['adjoint']['surface_integral'] == 'grounded':
    #  lam_nx.vector()[model.shf_dofs] = 0.0
    #  lam_ny.vector()[model.shf_dofs] = 0.0

    ## function assigner translates between mixed space and P1 space :
    #U_sp = model.U.function_space()
    #assx = FunctionAssigner(U_sp.sub(0), lam_nx.function_space())
    #assy = FunctionAssigner(U_sp.sub(1), lam_ny.function_space())

    #assx.assign(lam_ix, lam_nx)
    #assy.assign(lam_iy, lam_ny)
    
    #solve(self.aw == self.Lw, model.Lam,
    #      solver_parameters = {"linear_solver"  : "cg",
    #                           "preconditioner" : "hypre_amg"},
    #      annotate=False)
    #print_min_max(norm(model.Lam), '||Lam||')
    print_min_max(self.Lam, 'Lam')


