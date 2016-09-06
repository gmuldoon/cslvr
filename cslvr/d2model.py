from fenics            import *
from dolfin_adjoint    import *
from cslvr.inputoutput import print_text, get_text, print_min_max
from cslvr.model       import Model
from pylab             import inf
import sys

class D2Model(Model):
  """ 
  """

  def __init__(self, mesh, out_dir='./results/', order=1, use_periodic=False):
    """
    Create and instance of a 2D model.
    """
    s = "::: INITIALIZING 2D MODEL :::"
    print_text(s, cls=self)
    
    Model.__init__(self, mesh, out_dir, order, use_periodic)
  
  def color(self):
    return '150'

  def generate_pbc(self):
    """
    return a SubDomain of periodic lateral boundaries.
    """
    s = "    - using 2D periodic boundaries -"
    print_text(s, cls=self)

    xmin = MPI.min(mpi_comm_world(), self.mesh.coordinates()[:,0].min())
    xmax = MPI.max(mpi_comm_world(), self.mesh.coordinates()[:,0].max())
    ymin = MPI.min(mpi_comm_world(), self.mesh.coordinates()[:,1].min())
    ymax = MPI.max(mpi_comm_world(), self.mesh.coordinates()[:,1].max())
    
    self.use_periodic_boundaries = True
    
    class PeriodicBoundary(SubDomain):
      
      def inside(self, x, on_boundary):
        """
        Return True if on left or bottom boundary AND NOT on one 
        of the two corners (0, 1) and (1, 0).
        """
        return bool((near(x[0], xmin) or near(x[1], ymin)) and \
                    (not ((near(x[0], xmin) and near(x[1], ymax)) \
                     or (near(x[0], xmax) and near(x[1], ymin)))) \
                     and on_boundary)

      def map(self, x, y):
        """
        Remap the values on the top and right sides to the bottom and left
        sides.
        """
        if near(x[0], xmax) and near(x[1], ymax):
          y[0] = x[0] - xmax
          y[1] = x[1] - ymax
        elif near(x[0], xmax):
          y[0] = x[0] - xmax
          y[1] = x[1]
        elif near(x[1], ymax):
          y[0] = x[0]
          y[1] = x[1] - ymax
        else:
          y[0] = x[0]
          y[1] = x[1]

    self.pBC = PeriodicBoundary()
  
  def set_mesh(self, mesh):
    """
    Sets the mesh.
    
    :param mesh : Dolfin mesh to be written
    """
    super(D2Model, self).set_mesh(mesh)
    
    s = "::: setting 2D mesh :::"
    print_text(s, cls=self)
    
    if self.dim != 2:
      s = ">>> 2D MODEL REQUIRES A 2D MESH, EXITING <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    else:
      self.num_facets = self.mesh.size_global(1)
      self.num_cells  = self.mesh.size_global(2)
      self.dof        = self.mesh.size_global(0)
    s = "    - %iD mesh set, %i cells, %i facets, %i vertices - " \
        % (self.dim, self.num_cells, self.num_facets, self.dof)
    print_text(s, cls=self)

  def generate_function_spaces(self, order=1, use_periodic=False):
    """
    Generates the appropriate finite-element function spaces from parameters
    specified in the config file for the model.
    """
    super(D2Model, self).generate_function_spaces(order, use_periodic)

    s = "::: generating 2D function spaces :::"
    print_text(s, cls=self)
    
    s = "    - 2D function spaces created - "
    print_text(s, cls=self)

  def calculate_boundaries(self, latmesh=False, mask=None, lat_mask=None,
                           adot=None, U_mask=None, mark_divide=False):
    """
    Determines the boundaries of the current model mesh
    """
    s = "::: calculating boundaries :::"
    print_text(s, cls=self)

    if lat_mask == None and mark_divide:
      s = ">>> IF PARAMETER <mark_divide> OF calculate_boundaries() IS " + \
          "TRUE, PARAMETER <lat_mask> MUST BE AN EXPRESSION FOR THE LATERAL" + \
          " BOUNDARIES <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
     
    # this function contains markers which may be applied to facets of the mesh
    self.ff      = FacetFunction('size_t', self.mesh)
    self.ff_acc  = FacetFunction('size_t', self.mesh)
    self.cf      = CellFunction('size_t',  self.mesh)
    dofmap       = self.Q.dofmap()

    S = self.S
    B = self.B
    
    # default to all grounded ice :
    if mask == None:
      mask = Expression('1.0', element=self.Q.ufl_element())
    
    # default to all positive accumulation :
    if adot == None:
      adot = Expression('1.0', element=self.Q.ufl_element())
    
    # default to U observations everywhere :
    if U_mask == None:
      U_mask = Expression('1.0', element=self.Q.ufl_element())

    self.init_adot(adot)
    self.init_mask(mask)
    self.init_U_mask(U_mask)

    if mark_divide:
      s = "    - marking the interior facets for incomplete meshes -"
      print_text(s, cls=self)
      self.init_lat_mask(lat_mask)

    self.S.set_allow_extrapolation(True)
    self.B.set_allow_extrapolation(True)
    self.mask.set_allow_extrapolation(True)
    self.adot.set_allow_extrapolation(True)
    self.U_mask.set_allow_extrapolation(True)
    self.lat_mask.set_allow_extrapolation(True)
    
    tol = 1e-6
    
    s = "    - marking boundaries - "
    print_text(s, cls=self)

    if latmesh:
      s = "    - using a lateral surface mesh - "
      print_text(s, cls=self)
      
      class GAMMA_S_GND(SubDomain):
        def inside(self, x, on_boundary):
          return mask(x[0], x[1], x[2]) <=  1.0 and on_boundary
      gamma_s_gnd = GAMMA_S_GND()

      class GAMMA_S_FLT(SubDomain):
        def inside(self, x, on_boundary):
          return mask(x[0], x[1], x[2]) >  1.0 and on_boundary
      gamma_s_flt = GAMMA_S_FLT()

      class GAMMA_U_GND(SubDomain):
        def inside(self, x, on_boundary):
          return abs(x[2] - S(x[0], x[1], x[2])) < tol \
                 and mask(x[0], x[1], x[2]) <= 1.0 \
                 and U_mask(x[0], x[1], x[2]) <= 0.0 and on_boundary
      gamma_u_gnd = GAMMA_U_GND()

      class GAMMA_U_FLT(SubDomain):
        def inside(self, x, on_boundary):
          return abs(x[2] - S(x[0], x[1], x[2])) < tol \
                 and mask(x[0], x[1], x[2]) >  1.0 \
                 and U_mask(x[0], x[1], x[2]) <= 0.0 and on_boundary
      gamma_u_flt = GAMMA_U_FLT()

      class GAMMA_B_GND(SubDomain):
        def inside(self, x, on_boundary):
          return abs(x[2] - B(x[0], x[1], x[2])) < tol \
                 and mask(x[0], x[1], x[2]) <= 1.0 and on_boundary
      gamma_b_gnd = GAMMA_B_GND()

      class GAMMA_B_FLT(SubDomain):
        def inside(self, x, on_boundary):
          return abs(x[2] - B(x[0], x[1], x[2])) < tol \
                 and mask(x[0], x[1], x[2]) >  1.0 and on_boundary
      gamma_b_flt = GAMMA_B_FLT()

      class GAMMA_L_OVR(SubDomain):
        def inside(self, x, on_boundary):
          return x[2] > -10 and x[2] < S(x[0], x[1], x[2]) - tol and on_boundary
      gamma_l_ovr = GAMMA_L_OVR()

      class GAMMA_L_UDR(SubDomain):
        def inside(self, x, on_boundary):
          return x[2] < 10 and x[2] < S(x[0], x[1], x[2]) - tol and on_boundary
      gamma_l_udr = GAMMA_L_UDR()

      class GAMMA_L_TRM(SubDomain):
        def inside(self, x, on_boundary):
          return lat_mask(x[0], x[1], x[2]) <= 0.0
      gamma_l_trm = GAMMA_L_TRM()

      gamma_s_flt.mark(self.ff, self.GAMMA_S_FLT)
      gamma_s_gnd.mark(self.ff, self.GAMMA_S_GND)
      gamma_l_ovr.mark(self.ff, self.GAMMA_L_OVR)
      gamma_l_udr.mark(self.ff, self.GAMMA_L_UDR)
      gamma_b_flt.mark(self.ff, self.GAMMA_B_FLT)
      gamma_b_gnd.mark(self.ff, self.GAMMA_B_GND)
      #gamma_u_flt.mark(self.ff, self.GAMMA_U_FLT)
      #gamma_u_gnd.mark(self.ff, self.GAMMA_U_GND)
      #if mark_divide: 
      #  gamma_l_trm.mark(self.cf, 1)
    
    else :
      s = "    - not using a lateral surface mesh - "
      print_text(s, cls=self)

      class GAMMA_GND(SubDomain):
        def inside(self, x, on_boundary):
          return mask(x[0], x[1]) <= 1.0
      gamma_gnd = GAMMA_GND()

      class GAMMA_FLT(SubDomain):
        def inside(self, x, on_boundary):
          return mask(x[0], x[1]) > 1.0
      gamma_flt = GAMMA_FLT()

      class GAMMA_U_GND(SubDomain):
        def inside(self, x, on_boundary):
          return     mask(x[0], x[1]) <= 1.0 and U_mask(x[0], x[1]) <= 0.0
      gamma_u_gnd = GAMMA_U_GND()

      class GAMMA_U_FLT(SubDomain):
        def inside(self, x, on_boundary):
          return     mask(x[0], x[1]) >  1.0 and U_mask(x[0], x[1]) <= 0.0 
      gamma_u_flt = GAMMA_U_FLT()

      gamma_gnd.mark(self.cf,   self.GAMMA_S_GND) # grounded, no U obs.
      gamma_flt.mark(self.cf,   self.GAMMA_S_FLT) # floating, no U obs.
      gamma_u_gnd.mark(self.cf, self.GAMMA_U_GND) # grounded, with U obs.
      gamma_u_flt.mark(self.cf, self.GAMMA_U_FLT) # floating, with U obs.
    
      self.N_GAMMA_S_GND = sum(self.ff.array() == self.GAMMA_S_GND)
      self.N_GAMMA_S_FLT = sum(self.ff.array() == self.GAMMA_S_FLT)
      self.N_GAMMA_U_GND = sum(self.ff.array() == self.GAMMA_U_GND)
      self.N_GAMMA_U_FLT = sum(self.ff.array() == self.GAMMA_U_FLT)
    
      # mark the divide if desired :  
      if mark_divide:
        class GAMMA_L_DVD(SubDomain):
          def inside(self, x, on_boundary):
            return lat_mask(x[0], x[1]) <= 0.0 and on_boundary
        gamma_l_dvd = GAMMA_L_DVD()
        gamma_l_dvd.mark(self.ff, self.GAMMA_L_DVD)
    
    s = "    - done - "
    print_text(s, cls=self)
    
    #s = "    - iterating through %i cells - " % self.num_cells
    #print_text(s, cls=self)
    #for c in cells(self.mesh):
    #  x_m     = c.midpoint().x()
    #  y_m     = c.midpoint().y()
    #  z_m     = c.midpoint().z()
    #  mask_xy = mask(x_m, y_m, z_m)

    #  if mask_xy > 1:
    #    self.cf[c] = 1
    #  else:
    #    self.cf[c] = 0

    #s = "    - done - "
    #print_text(s, cls=self)

    self.set_measures(self.ff, self.cf)
    
  def set_subdomains(self, f):
    """
    Set the facet subdomains FacetFunction self.ff, cell subdomains
    CellFunction self.cf, and accumulation FacetFunction self.ff_acc from
    MeshFunctions saved in an .h5 file <f>.
    """
    s = "::: setting 2D subdomains :::"
    print_text(s, cls=self)

    self.ff     = MeshFunction('size_t', self.mesh)
    self.cf     = MeshFunction('size_t', self.mesh)
    self.ff_acc = MeshFunction('size_t', self.mesh)
    f.read(self.ff,     'ff')
    f.read(self.cf,     'cf')
    f.read(self.ff_acc, 'ff_acc')

    self.set_measures(self.ff, self.cf)

  def deform_mesh_to_geometry(self, S, B):
    """
    Deforms the 2D mesh to the geometry from FEniCS Expressions for the 
    surface <S> and bed <B>.
    """
    s = "::: deforming mesh to geometry :::"
    print_text(s, cls=self)

    self.init_S(S)
    self.init_B(B)
    
    # transform z :
    # thickness = surface - base, z = thickness + base
    # Get the height of the mesh, assumes that the base is at z=0
    max_height  = self.mesh.coordinates()[:,2].max()
    min_height  = self.mesh.coordinates()[:,2].min()
    mesh_height = max_height - min_height
    
    s = "    - iterating through %i vertices - " % self.dof
    print_text(s, cls=self)
    
    for x in self.mesh.coordinates():
      x[2] = (x[2] / mesh_height) * ( + S(x[0],x[1],x[2]) \
                                      - B(x[0],x[1],x[2]) )
      x[2] = x[2] + B(x[0], x[1], x[2])
    s = "    - done - "
    print_text(s, cls=self)
    
  def calc_thickness(self):
    """
    Calculate the continuous thickness field which increases from 0 at the 
    surface to the actual thickness at the bed.
    """
    s = "::: calculating z-varying thickness :::"
    print_text(s, cls=self)
    #H = project(self.S - self.x[2], self.Q, annotate=False)
    H          = self.vert_integrate(Constant(1.0), d='down')
    Hv         = H.vector()
    Hv[Hv < 0] = 0.0
    print_min_max(H, 'H', cls=self)
    return H
  
  def solve_hydrostatic_pressure(self, annotate=True):
    """
    Solve for the hydrostatic pressure 'p'.
    """
    # solve for vertical velocity :
    s  = "::: solving hydrostatic pressure :::"
    print_text(s, cls=self)
    rhoi   = self.rhoi
    g      = self.g
    #S      = self.S
    #z      = self.x[2]
    #p      = project(rhoi*g*(S - z), self.Q, annotate=annotate)
    p      = self.vert_integrate(rhoi*g, d='down')
    pv     = p.vector()
    pv[pv < 0] = 0.0
    self.assign_variable(self.p, p)
  
  def vert_extrude(self, u, d='up', Q='self'):
    r"""
    This extrudes a function *u* vertically in the direction *d* = 'up' or
    'down'.  It does this by solving a variational problem:
  
    .. math::
       
       \frac{\partial v}{\partial z} = 0 \hspace{10mm}
       v|_b = u

    """
    s = "::: extruding function %s :::" % d
    print_text(s, cls=self)
    if type(Q) != FunctionSpace:
      Q  = self.Q
    ff   = self.ff
    phi  = TestFunction(Q)
    v    = TrialFunction(Q)
    a    = v.dx(2) * phi * dx
    L    = DOLFIN_EPS * phi * dx
    bcs  = []
    # extrude bed (ff = 3,5) 
    if d == 'up':
      if self.N_GAMMA_B_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_B_GND))  # grounded
      if self.N_GAMMA_B_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_B_FLT))  # shelves
    # extrude surface (ff = 2,6) 
    elif d == 'down':
      if self.N_GAMMA_S_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_S_GND))  # grounded
      if self.N_GAMMA_S_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_S_FLT))  # shelves
      if self.N_GAMMA_U_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_U_GND))  # grounded
      if self.N_GAMMA_U_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_U_FLT))  # shelves
    name = '%s extruded %s' % (u.name(), d)
    v    = Function(Q, name=name)
    solve(a == L, v, bcs, annotate=False)
    print_min_max(u, 'function to be extruded')
    print_min_max(v, 'extruded function')
    return v
  
  def vert_integrate(self, u, d='up', Q='self'):
    """
    Integrate <u> from the bed to the surface.
    """
    s = "::: vertically integrating function :::"
    print_text(s, cls=self)

    if type(Q) != FunctionSpace:
      Q = self.Q
    ff  = self.ff
    phi = TestFunction(Q)
    v   = TrialFunction(Q)
    bcs = []
    # integral is zero on bed (ff = 3,5) 
    if d == 'up':
      if self.N_GAMMA_B_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_B_GND))  # grounded
      if self.N_GAMMA_B_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_B_FLT))  # shelves
      a      = v.dx(2) * phi * dx
    # integral is zero on surface (ff = 2,6) 
    elif d == 'down':
      if self.N_GAMMA_S_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_S_GND))  # grounded
      if self.N_GAMMA_S_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_S_FLT))  # shelves
      if self.N_GAMMA_U_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_U_GND))  # grounded
      if self.N_GAMMA_U_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_U_FLT))  # shelves
      a      = -v.dx(2) * phi * dx
    L      = u * phi * dx
    name   = 'value integrated %s' % d 
    v      = Function(Q, name=name)
    solve(a == L, v, bcs, annotate=False)
    print_min_max(u, 'vertically integrated function')
    return v

  def calc_vert_average(self, u):
    """
    Calculates the vertical average of a given function space and function.  
    
    :param u: Function representing the model's function space
    :rtype:   Dolfin projection and Function of the vertical average
    """
    H    = self.S - self.B
    uhat = self.vert_integrate(u, d='up')
    s = "::: calculating vertical average :::"
    print_text(s, cls=self)
    ubar = project(uhat/H, self.Q, annotate=False)
    print_min_max(ubar, 'ubar')
    name = "vertical average of %s" % u.name()
    ubar.rename(name, '')
    ubar = self.vert_extrude(ubar, d='down')
    return ubar

  def initialize_variables(self):
    """
    Initializes the class's variables to default values that are then set
    by the individually created model.
    """
    super(D2Model, self).initialize_variables()

    s = "::: initializing 2D variables :::"
    print_text(s, cls=self)

    # Depth below sea level :
    class Depth(Expression):
      def eval(self, values, x):
        values[0] = abs(min(0, x[2]))
    self.D = Depth(element=self.Q.ufl_element())
    
    # Enthalpy model
    self.theta0        = Function(self.Q, name='theta0')
    self.W0            = Function(self.Q, name='W0')
    self.thetahat      = Function(self.Q, name='thetahat')
    self.uhat          = Function(self.Q, name='uhat')
    self.vhat          = Function(self.Q, name='vhat')
    self.what          = Function(self.Q, name='what')
    self.mhat          = Function(self.Q, name='mhat')

    # Surface climate model
    self.precip        = Function(self.Q, name='precip')



