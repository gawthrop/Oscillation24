""" Stoichiometric analysis using BondGraphTools """
import BondGraphTools as bgt
import numpy as np
import sympy
import copy
import scipy.integrate as sci
import scipy.constants as const
import matplotlib.pyplot as plt
import networkx as nx
import itertools
import control as con

def F():
    """ Faraday's constant """
    F = const.physical_constants['Faraday constant'][0]
    return F

def k_bolt():
    """ Boltzmann's constant """
    k_bolt = const.physical_constants['Boltzmann constant'][0]
    return k_bolt

def R():
    """ Gas constant """
    R = const.physical_constants['molar gas constant'][0]
    return R


def RT(T_cent=37):
    """ Gas constant * Temperature """
    T = 273.15 + T_cent         # Human temperature deg K
    return R()*T

def kT(T_cent=37):
    """ Boltzmann's constant * Temperature """
    T = 273.15 + T_cent         # Human temperature deg K
    return k_bolt()*T

def V_N(T_cent=37,Normalise=False):
    """The V_N constant (=RT/F).
    """
    if Normalise:
        V_N = 1
    else:
        V_N = RT(T_cent)/F()
        
    return V_N

def indices(list,element):
    """ Find all indices of matching elements in list
    """

    indexList = [i for i, x in enumerate(list) if x == element]
    return indexList

def getName(sys,name):
    """ 
    Find the name of the component corresponding to a state
    """
    if name[0] == 'x':
        var = sys.state_vars[name]
    elif name[0] == 'u':
        var = sys.control_vars[name]
    else:
        print("Cannot process", name)
            
    comp = var[0]
    name = var[1]

    # ## Assume that Re components are called r something (yuk)
    # if (name[0] == 'u') and (comp.name[0] == 'r'):
    #     #name = comp.parent.name+':'+comp.name
    #     name = comp.name
    # else:
    #     if comp.metamodel == 'BG':
    #         name = getName(comp,name)
    #     else:
    #         name = comp.name
    if comp.metamodel == 'BG':
        name = getName(comp,name)
    else:
        name = comp.name
    return name
    
   

##Parameter setting function (by name)
def set_param_by_name(model,comp_name,par_name,value):
    comp = model / comp_name
    bgt.set_param(comp, par_name, value)

##Parameter get value function (by name)
def get_param_by_name(model,comp_name,par_name):
    comp = model / comp_name
    # print("comp:",comp)
    # print("comp.params:",comp.params)
    return  comp.params[par_name]["value"]

def hp(x,y):
    """Hadamard product: Elementwise product of two vectors"""
    return sympy.matrix_multiply_elementwise(x,y)
    
def Exp(x,lin=[]):
    """Elementwise exponent of vector"""
    ex = sympy.Matrix([])
    V_N = sympy.symbols('V_N')
    for i,x_i in enumerate(x):
        if i in lin:
            ex_i = x_i/V_N
        else:
            ex_i = sympy.exp(x_i)
        ex = ex.row_insert(i,sympy.Matrix([ex_i]))
    return ex

def Log(x,lin=[]):
    """Elementwise log of vector"""
    V_N = sympy.symbols('V_N')
    lx = sympy.Matrix([])
    for i,x_i in enumerate(x):
        if i in lin:
            lx_i = x_i/V_N
        else:
            lx_i = sympy.log(x_i)
        lx = lx.row_insert(i,sympy.Matrix([lx_i]))
    return lx

def Logn(x,lin=[],makePositive=True,Normalise=False):
    """Numerical elementwise log of vector"""
    lx = np.zeros(x.shape)
    for i,x_i in enumerate(x):
        if i in lin:
            lx_i = x_i/V_N(Normalise=Normalise)
        else:
            min_i = np.min(x_i)
            if makePositive and (min_i < 0):
                xx_i = x_i - min_i + 1e-20
            else:
                xx_i = x_i
                
            lx_i = np.log(xx_i)
        
        lx[i] = lx_i
        
    return np.array(lx)

def vec(species,label="x"):
    """Create col. vector of symbolic states"""
    st = sympy.Matrix([])
    for i,spec in enumerate(species):
        spec_str = label+"_"+spec
        spec_sym = sympy.symbols(spec_str)
        st = st.row_insert(i,sympy.Matrix([spec_sym]))

    return st

def par_vec(model,names,par):

    Par = sympy.Matrix([])
    for i,name in enumerate(names):
        val = get_param_by_name(model,name,par)
        Par = Par.row_insert(i,sympy.Matrix([val]))

    return Par

def flow(s,sf=None,alpha=1):

    if sf is None:
        ZZ = s["Z"]
        DD = s["D"]
    else:
        ZZ = sf["Z"]
        DD = sf["D"]
        
    V_N = sympy.symbols("V_N")
    species = s["species"]
    reaction = s["reaction"]
    K_s = s["K_s"]
    kappa = s["kappa"]
    i_lin = s["i_lin"]
    j_lin = s["j_lin"]
    Z = sympy.Matrix(ZZ)/alpha
    D = sympy.Matrix(DD)
    kx = hp(K_s,vec(species,"x"))
    Phi_c = Z.T*Log(kx,i_lin)   # Complex potentials
    v0 = -D.T*Exp(Phi_c) # Nonlinear flows (mass-action)
    v0_lin =  -D.T*Phi_c*V_N # Linear flows
    ##v0[j_lin] = v0_lin[j_lin]
    for j,v0j in enumerate(v0):
        if j in j_lin:
            v0[j] = sympy.simplify(v0_lin[j])
        else:
            v0[j] = sympy.simplify(v0[j])
            
    v = hp(kappa,v0)
    return v,v0

def dflow(s,sf=None):
    """ Find matrix for linearised system:
        dv is dv/dx; dv0 is without kappa
    """
    v,v0 = flow(s,sf=sf)
    x = vec(s["species"])
    dv = sympy.Matrix([])
    dv0 = sympy.Matrix([])
    
    for i,x_i in enumerate(x):
        dv_i = sympy.diff(v,x_i)
        dv = dv.col_insert(i,sympy.Matrix([dv_i]))
        dv0_i = sympy.diff(v0,x_i)
        dv0 = dv0.col_insert(i,sympy.Matrix([dv0_i]))

    return dv,dv0

def rat2int(N):
    """Convert a rational matrix to an integer matrix.

    Parameters:
    N: numpy rational array

    Returns:
    mN:  numpy rational array

    mN is m*N where m is the least common multiple of all denominators

     Example:
    >>> n1 = sympy.Matrix([2,1]); n2 = sympy.Matrix([4,6]); N = sympy.Matrix([n1/2,n2/3])
    >>> print(N)
    Matrix([[1], [1/2], [4/3], [2]])
    >>> print(stoich.rat2int(N))
    Matrix([[6], [3], [8], [12]])
    """
    n,m = N.shape
 
    lcm_den = 1;
    for i in range(n):
        for j in range(m):
            num,den = sympy.fraction(N[i,j])
            lcm_den = sympy.lcm(lcm_den,den)
            #print(num,den,lcm_den)

    return lcm_den*N;      # Make integer

def inull(NN,integer=False,symbolic=False):
    """ Integer null space matrix of integer matrix NN.

    Parameter:
    NN : numpy array

    Returns:
    null  : numpy array with columns null space vectors

    Example:
    >>> N = np.array([[-1,1],[1,-1]]); print(N)
    [[-1  1]
    [ 1 -1]]
    >>> null = stoich.inull(N); print(null)
    [[1]
    [1]]
    """

    N = sympy.Matrix(NN)            # Symbolic form
    
    ## Use sympy to compute null space - list of vectors
    null_list = sympy.simplify(N, rational=True).nullspace()
    
    ## Create matrix with null-space vectors as columns
    nullN = sympy.Matrix([])
    for j,vec in enumerate(null_list):
        if integer:
            vec = rat2int(vec)      # Make integer from rational
            
        nullN = nullN.col_insert(j,vec)

    ## Return as numpy array
    if integer and (not symbolic):
        return np.array(nullN).astype(int)
    else:
        return np.array(nullN)

def xX(N,G,symbolic=False,integer=False):
    """Matrices to transform between full state X and reduced state x.

    Parameters:
    N: stoichimetric matrix (numpy array)

    Returns: L_xX,L_Xx,G_X
    
    x = L_xX*X
    X = L_Xx*x + G_X*X_0

    See: Peter J. Gawthrop and Edmund J. Crampin, 
    "Energy-based analysis of biochemical cycles using bond graphs",
    Proc. R. Soc. A 470: 20140459.
    DOI: 10.1098/rspa.2014.0459
    """

    ## Sizes
    nn = N.shape
    n_X = nn[0]
    n_V = nn[1]
    
    NN = sympy.Matrix(N)           # Convert to sympy
    NNT = NN.T
    res = NNT.rref();            # Use sympy rref
    RRT = res[0].T
    i_x = res[1]
    ## print(i_x)
    n_x = len(i_x)
    i_d = tuple(np.setdiff1d(range(0,n_X),i_x))
    L_Xx = RRT[:,0:n_x];
    
    ## LxX: convert from X to x
    I = sympy.eye(n_X)
    L_xX = I[i_x,:]
    L_dX = I[i_d,:]

    ## G_X: add in the chemostats.
    if (n_x>0):
        #G_X = I - L_Xx*L_xX
        G_X = L_dX.T*G
    else:
       G_X = I 

    if not symbolic:
        if integer:
            L_xX = np.array(L_xX).astype(int)
            L_dX = np.array(L_dX).astype(int)
            L_Xx = np.array(L_Xx).astype(int)
            G_X = np.array(G_X).astype(int)
        else:
            L_xX = np.array(L_xX).astype(float)
            L_dX = np.array(L_dX).astype(float)
            L_Xx = np.array(L_Xx).astype(float)
            G_X = np.array(G_X).astype(float)

    return L_xX, L_Xx, G_X, L_dX, list(i_x)

def N2ZD(Nf,Nr,symbolic=False):
    """Decompose stoichiometric matrix N as N = ZD.

    Parameters:
    Nf : numpy array -- the forward stoichiometric matrix
    Nr : numpy array -- the reverse stoichiometric matrix

    where N = Nr - Nf.

    Returns:
    Z : numpy array -- matrix of (chemical) complexes
    D : numpy array -- incidence matrix of network digraph

    Example:
    >>> Nf = np.array([[1, 0],[0, 0],[0, 1],[1, 0]])
    >>> Nr = np.array([[0, 0],[0, 1],[1, 0],[0, 1]])
    >>> Z,D =  N2ZD(Nf,Nr)
    >>> Z
    array([[1, 0, 0],
          [0, 0, 1],
          [0, 1, 0],
          [1, 0, 1]])
    >>> D
    array([[-1,  0],
           [ 1, -1],
           [ 0,  1]])

    See:
    P.J. Gawthrop and E.J. Crampin. 
    Bond graph representation of chemical reaction networks. 
    IEEE Transactions on NanoBioscience, 17(4):1--7, October 2018.
    """
    
    ## Number of reactions
    n = Nf.shape[1]

    ## Create Nfr
    Nfr = np.block([Nf,Nr])

    ## Z^T with duplicate rows
    ZT = Nfr.T

    ## Initial D
    eye = np.eye(n).astype(int)
    D = np.block([-eye,eye]).T

    if not symbolic:
        ## Find I_u, indices of unique rows of Z^T
        U, I_u = np.unique(ZT, axis=0, return_index=True)

        ## Sort indices to retain row order
        I_u = np.sort(I_u)

        ## Find I_d, indices of the duplicate rows
        I_d = np.setdiff1d(np.arange(2*n), I_u)

        ## Add duplicate rows of D to the unique rows.
        for i_d in I_d:
            Z_d = ZT[i_d]
            for i_u in I_u:
                Z_u = ZT[i_u]
                if np.array_equal(Z_u,Z_d):
                    D[i_u] += D[i_d]

        ## ZT contains the unique rows
        ZT = ZT[I_u]

        ## D contains the corresponding rows
        D = D[I_u]

        
    Z = ZT.T                    # Z itself

 
    # ## Zap zero columns of Z (!)
    # j_zero = np.where(~Z.any(axis=0))[0]
    # print(j_zero,len(j_zero))
    # if len(j_zero)>0:
    #     Z = np.delete(Z,j_zero,axis=1)

    # ## Zap zero columns of D (!)
    # j_zero = np.where(~D.any(axis=0))[0]
    # print(j_zero,len(j_zero))
    # if len(j_zero)>0:
    #     D = np.delete(D,j_zero,axis=1)
        
    return Z,D

def get_comp_names(model,comp_type='C',n_ports=1,linear=[]):

    """Get list of all component names of type comp_type."""

    comp_names = []; i_comp = []; comp_index = {}; i_lin = []; par_name = [];
    index = 0

    if comp_type in ['C']:
        variables = model.state_vars
    elif comp_type in ['R']:
        variables = model.control_vars
    else:
        print("*** comp_type", comp_type, "unknown")
        
    index = 0
    for i,var in enumerate(variables):

        if (i % n_ports) == 0:
            #print(i,index,var)
            name = getName(model,var)
            #print(name)
            comp_names.append(name)
            comp_index[name] = index
            
            ## Detect linear components
            # is_linear = (("base/" in comp.template) or
            #              (comp.name in linear)
            # )
            is_linear = name in linear
            
            if is_linear:
                i_lin.append(index)
                par_Name = {"C":"C","R":"r"}
            else:
                par_Name = {"C":"k","R":"r"}

            if comp_type in ['C']:
                par_name.append('K_'+name)
            elif comp_type in ['R']:
                par_name.append('kappa_'+name)
            else:
                print("*** comp_type", comp_type, "unknown")
                
            index += 1
            
    return comp_names,i_comp,comp_index,i_lin,par_name

# def get_comp_names(model,comp_type='C',n_ports=1,linear=[]):

#     """Get list of all component names of type comp_type."""

#     comp_names = []; i_comp = []; comp_index = {}; i_lin = []; par_name = [];
#     index = 0

#     for i,comp in enumerate(model.components):
#         ## Detect relevent components
#         ## and derive parameter names from symbolic values.
#         if comp.metamodel==comp_type:
        
#             ## Detect linear components
#             is_linear = (("base/" in comp.template) or
#                          (comp.name in linear)
#             )

#             if is_linear:
#                 i_lin.append(index)
#                 par_Name = {"C":"C","R":"r"}
#             else:
#                 par_Name = {"C":"k","R":"r"}

#             if len(comp.ports)==n_ports:
#                 comp_names.append(comp.name)
#                 i_comp.append(i)
#                 comp_index[comp.name] = index
#                 par_name.append(str(comp.params[par_Name[comp_type]]["value"]))
#                 index += 1
    
#     return comp_names,i_comp,comp_index,i_lin,par_name
        
def get_species(model,linear=[]):

    """Get list of all species."""
    
    return get_comp_names(model,comp_type='C',linear=linear)

def get_reactions(model,linear=[]):

    """Get list of all reactions."""
    
    return get_comp_names(model,comp_type='R',n_ports=2,linear=linear)

def ReSS(name):

    model = bgt.new(name=name)

    ## SS components for forward and reverse flows.
    SS_f =  bgt.new("Sf", name=name)
    SS_r =  bgt.new("Sf", name=name+"_r")

    ## SS components for forward and reverse ports.
    port_f =  bgt.new("SS", name="port_f")
    port_r =  bgt.new("SS", name="port_r")

    ## Zero junctions to put them on
    zero_f =  bgt.new("0", name="zero_f")
    zero_r =  bgt.new("0", name="zero_r")
    
    ## Add them
    bgt.add(model,
            SS_f, SS_r,
            port_f, port_r,
            zero_f, zero_r)

    ## Connect them
    bgt.connect(port_f,zero_f)
    bgt.connect(zero_f,SS_f)
 
    bgt.connect(zero_r,port_r)
    bgt.connect(zero_r,SS_r)

    ## Expose the ports
    bgt.expose(port_f,'f')
    bgt.expose(port_r,'r')

    return model

def replaceRe(model,quiet=False):

    SfStr = "{0} = bgt.new('Sf',name='{0}')\n"
    components = copy.copy(model.components)
    #print(model.bonds)
    for comp in components:
        if comp.metamodel in ['BG']:
            replaceRe(comp,quiet=quiet)
            
        if comp.metamodel in ['R']:
            
            name = comp.name
            if not quiet:
                print("Swapping Re:" + name, "for two Sf in", model.name)
            
            ## Find what it is connected to, and disconnect
            forward_comp = None
            reverse_comp = None
            bonds = copy.copy(model.bonds) # ????
            for bond in bonds:
                #print(bond)
                ## Forward connection
                # print(comp.name, bond.head.component.name, comp.name is bond.head.component.name)
                # print(comp.name, bond.tail.component.name, comp.name is bond.tail.component.name)
                if bond.head.component.name is comp.name:
                    forward_comp = bond.tail.component
                    # print("forward:", forward_comp, bond.tail) 
                    bgt.disconnect(forward_comp,comp)

                    
                ## Reverse connection
                if bond.tail.component.name is comp.name:
                    reverse_comp = bond.head.component
                    # print ("reverse:",reverse_comp)
                    bgt.disconnect(comp,reverse_comp)
                        
            ## Remove the Re
            #name = comp.name;
            bgt.remove(model, comp)
                        
            ## Add the new ReSS
            new_comp = ReSS(name);
            bgt.add(model,new_comp);
        
            ## and reconnect
            # if not quiet:
            #     print("forward:", forward_comp)
            #     print ("reverse:",reverse_comp)
                
            if not forward_comp is None:
                bgt.connect(forward_comp,(new_comp,0))
            else:
                print('No forward component')
                
            if not reverse_comp is None:
                bgt.connect((new_comp,1),reverse_comp)
            else:
                print('No reverse component')
            # ## Create two Sf components instead
            # name_f = name+"_Sf_f"
            # name_r = name+"_Sf_r"
            # print(name_f,name_r)
            # # exec(SfStr.format(name_f))
            # # exec(SfStr.format(name_r))
            # Sf_f = bgt.new("Sf",name=name_f)
            # Sf_r = bgt.new("Sf",name=name_r)
            # ## and reconnect
            # bgt.connect(forward_comp,Sf_f)
            # bgt.connect(Sf_r,reverse_comp)     

    #return model
    
def sprint(s,name="N"):
    """Print some stoichiometric information
    
    Parameters:
    s: output from stoich
    name: name of element to be printed
    """
    print(name+":\n",s[name])

def sprints(s):
    """Print all stoichiometric information
    
    Parameter:
    s: output from stoich
    """

    for item in s:
        name = item
        sprint(s,name)

# def pmatrix(a):
#     """Returns a LaTeX pmatrix

#     :a: numpy array
#     :returns: LaTeX pmatrix as a string
#     """
#     if len(a.shape) > 2:
#         raise ValueError('pmatrix can at most display two dimensions')
#     lines = str(a).replace('[', '').replace(']', '').splitlines()
#     rv = [r'\begin{pmatrix}']
#     rv += ['  ' + ' & '.join(l.split()) + r'\\' for l in lines]
#     rv +=  [r'\end{pmatrix}']
#     return '\n'.join(rv)

def sprintl(s,name="N",align=True,transpose=False):
    """LaTeX-printable string of some stoichiometric information
    
    Parameters:
    s: output from stoich
    name: name of element to be printed
    align: bracket with LaTeX align environment
    """
    indent = "    "
    mname = {}
    mname["species"] = "X"
    mname["species_x"] = "x"
    mname["reaction"] = "V"
    if align:
        str = "\\begin{align}\n"
    else:
        str = ""
        
    if name in ["species","species_x","reaction"]:
        str =  str + mname[name] + "&= \\begin{pmatrix}\n"
        names = s[name]
        for nam in names:
            str = str + indent + mname[name] + "_{"+nam+"}\\\\\n"
        str = str + "\\end{pmatrix}"
    else:
        if transpose:
            mat = sympy.latex(sympy.Matrix(s[name].T),mat_delim="(")
            str = str + name + "^T &=\n" + mat
        else:
            mat = sympy.latex(sympy.Matrix(s[name]),mat_delim="(")
            str = str + name + " &=\n" + mat

    if align:
        str = str + "\n\\end{align}\n"
        
    return str

def sprintvl(s,alpha=1,align=True,split=10):
    """LaTeX-printable string of flow equations
    
    Parameters:
    s: output from stoich
    align: bracket with LaTeX align environment
    """

    env = 'align'
    be = '\\begin{'+env+'}\n'
    ee = '\\end{'+env+'}\n'
    dx = be

    if align:
        str = be
    else:
        str = ""

    v,v0 = flow(s,alpha=alpha)
    V = vec(s["reaction"],"v")
    ii = 0
    for i,v_i in enumerate(v):
        str += sympy.latex(V[i])
        str += " &= "
        str += sympy.latex(v_i,mat_delim="(")
        ii += 1
        if ii==split:
            str += '\n' + ee + be
            ii = 0
        else:
            str += "\\\\\n"

    str = str[:-3]
    if align:
        str = str + '\n' + ee
        
    return str

def sprintp(s,printReac=False,chemformula=False,removeSingle=False):
    """ Print the pathways
    """
    K = s['K']
    if removeSingle:
        KK = singleRemove(K)
    else:
        KK = K

    reaction = s['reaction']
    nP = KK.shape[1]
    if removeSingle:
         print(nP,'non-unit pathways')
    else:
        print(nP,'pathways')
        
    if chemformula:
        out = "\n\\begin{enumerate}\n"
    else:
        out = ""
        
    reacOut = ""
    for i in range(nP):
        if chemformula:
            out += "\item \\ch{"
        else:
            out += str(i)+": "
        reacs = []
        for j in range(s['n_V']):
            reac = s["reaction"][j].replace('__','.')
            k = KK[j,i]
            if abs(k)>0:
                reacs.append(reac)
                if k<0:
                    out += " - "
                else:
                    out += " + "
                if abs(k)>1:
                    out += str(abs(k))+" "
                out += reac
        if chemformula:
            out += '}'


        if printReac:
            reacOut += sprintrl(s,chemformula=True,reaction=reacs)
        out += "\n"

    if chemformula:
        out += '\end{enumerate}\n'

    if printReac:
        return reacOut
    else:
        return out

def prodStoichName(stoich,name):
    """ Product of stoichiometry and a list of names """

    (n,m) = stoich.shape

    prods = []
    for i in range(n):
        prod = ""
        for j in range(m):
            spec = name[j].replace('__','.')
            if stoich[i,j] != 0:
                if (stoich[i,j]!=1):
                    prod += str(stoich[i,j])+" "
                prod += spec+" + "
        prod = prod.replace("+ -","- ")
        prod = prod.replace("- 1","- ")
        prod = prod.replace("-1","- ")
        prods.append(prod[:-3])
    return prods

def sprintdxl(s,sc,split=10):
    """LaTeX-printable string of state equations
    
    Parameters:
    s: output from stoich
    sc: s with chemostats
    split: split at this number of equations
    """

    env = 'align'
    be = '\\begin{'+env+'}\n'
    ee = '\\end{'+env+'}\n'
    dx = be
    
    rname = s['reaction']
    sname = s['species']
    chemostats = sc['chemostats']
    nState = len(sname)-len(chemostats)
    
    vname = []
    for name in rname:
        name = name.replace('_','')
        vname.append('v_{'+name+'}')

    RHS = prodStoichName(s['N'],vname)
    ii = 0
    j = 0
    for i,spec in enumerate(sname):
        Spec = spec.replace('_','')
        if not spec in chemostats:
            j += 1
            ii += 1
            dx += '\\dot{x}_{'+Spec+'} &= ' + RHS[i]
            if (ii==split) and (j<nState):
                dx += '\n'+ee+be
                ii = 0
            else:
                dx += '\\\\\n'

    return dx[:-3]+'\n'+ee
    
def sprintparl(parameter,split=10):
    """LaTeX-printable string of parameters
    
    Parameters:
    parameters: system parameters
    split: split at this number of equations
    """

    env = 'align'
    be = '\\begin{'+env+'}\n'
    ee = '\\end{'+env+'}\n'
    str = be
    nPar = len(parameter)

    ii = 0
    for i,par in enumerate(parameter):
        #Spec = spec.replace('_','')
        ii += 1
        param = parameter[par]
        
        par = par.replace('_','')
        par = par.replace('K','K_{',1)
        par = par.replace('kappa','\\kappa_{',1)
        par += '}'
        str += f'{par} &= {param:.4g}'
        if (ii==split) and (i<nPar-1):
            str += '\n'+ee+be
            ii = 0
        else:
            str += '\\\\\n'

    return str[:-3]+'\n'+ee
    
def reacSym(reac,s,chemformula=False):
    """ Reaction symbol """

    if 'UniDir' in s.keys():
        UniDir = s['UniDir']
    else:
        UniDir = None
        
    if UniDir is not None:
        uni = reac in UniDir
    else:
        uni = False
        
    if chemformula:
        if uni:
            eq = "& -> "
        else:
            eq = "& <> "
    else:
        if uni:
            eq = " &\\rightarrow "
        else:
            eq = " &\\Leftrightarrow "

    return eq

def sprintrl(s,align=True,chemformula=False,split=10,reaction=[],all=False,Phi=None,units="",showMu=False):
    """ Print the chemical reactions in LaTeX.
        usepackage{chemformula}
    """
    ## Forward and reverse stoichiometric matrices
    if all:
        Nf = s["Nf"]
        Nr = s["Nr"]
    else:
        N = s["N"]
        Nf = -N*(N<0)
        Nr = N*(N>0)
        
    n = Nf.shape[0]
    m = Nf.shape[1]

    if chemformula:
        prefix = "\\ch{"
        postfix = "}"
        eq = "&<>"
    else:
        prefix = ""
        postfix = ""
        eq = " &\\Leftrightarrow "

    if Phi is None:
        nn = ""
        env = "align"
    else:
        nn = "{2}"
        env = "xalignat*"
    if align:
        reacStr = "\\begin{"+env+"}"+nn+"\n"
    else:
        reacStr = ""

    if len(reaction)==0:
        J = np.arange(0,m)
    else:
        J = []
        for j,reac in enumerate(s['reaction']):
            if reac in reaction:
                J.append(j)
            
    for j in J:
        substrate = ""
        product = ""
        if Phi is None:
            Postfix = postfix
        else:
            Ph = Phi.flatten()[j]
            if 'mV' in units:
                Units = r'~\text{mV}'
                Postfix = postfix + "&&" + "({}{})".format(int(round(1000*Ph)),Units)
            else:
                Postfix = postfix + "&&" + "({:02.2f}{})".format(Ph,units)
            if showMu:
                F = const.physical_constants['Faraday constant'][0]
                if 'kJ' in units:
                    Units = r'~\text{kJ mol}^{-1}'
                    Postfix += "\\;[" +"{:02.2f}{}".format(-Ph*F/1000,Units) + "]"
                else:
                    Postfix += "\\;[" +"{:02.2f}".format(-Ph*F/1000) + "]"
            
        #for i in np.arange(0,n):
        for i,Spec in enumerate(s["species"]):
            #spec = s["species"][i].replace('__','.')
            #spec = Spec.replace('__','.')
            spec = Spec.replace('_','')
            if Nf[i,j]>0:
                if (Nf[i,j]!=1):
                    substrate += str(Nf[i,j])+" "
                substrate += spec+" + "
            if Nr[i,j]>0:
                if (Nr[i,j]!=1):
                    product += str(Nr[i,j])+" "
                product += spec+" + "

        #reac = s["reaction"][j].replace('__','.')
        reac = s["reaction"][j].replace('_','')
        eq = reacSym(reac,s,chemformula) 
        reacStr += prefix + substrate[:-2] +  eq
        if chemformula:
            reacStr += "[ " + reac + " ] "
        reacStr +=  product[:-2] + Postfix +"\\\\\n"

        jj = j % split          # j modulo split

        if (jj == (split-1)) and (j<m-1):
            reacStr = reacStr[:-3]
            if align:
                reacStr += "\n\\end{"+env+"}\n"
                reacStr += "\n\\begin{"+env+"}"+nn+"\n"

    reacStr = reacStr[:-3]
    if align:
        reacStr += "\n\\end{"+env+"}\n"
        
    return reacStr

def pool(s,removeSingle=True):
    """ Find stoichiometry representing pools (conserved moieties)
    """
    ss = {}
    G = s['G']
    ## Effective stoichiometric matrix is G transpose
    N = G.T
    if removeSingle:             # Remove single reaction paths
        N = singleRemove(N)
    ss['N'] = N

    ## Create pseudo reaction names
    n_M = N.shape[1]
    name = []
    for i in range(n_M):
        name.append('m_'+str(i))
    ss['reaction'] = name

    ## Species are the same
    ss['species'] = s['species']

    ## Sizes
    ss['n_X'] = s['n_X']
    ss['n_V'] = n_M

    return ss

    #sprints(ss)

def sprintml(s,align=True,chemformula=False,split=10):
    """Print conserved moieties in LaTeX form
    """
    ss = pool(s)
    return sprintrl(ss,align=align,chemformula=chemformula,split=split)

def getStoich(model,linear=[],chemostats=[],symbolic=False,quiet=False):

    ## Swap Re components for ReSS
    replaceRe(model,quiet=quiet)

    ## Get lists of species and reactions
    species,i_spec,spec_index,i_lin,spec_par_name = get_species(model,
                                                                linear=linear)
    reaction,i_reac,reac_index,j_lin,reac_par_name = get_reactions(model,
                                                                      linear=linear)
    sr = species + reaction
    
    ## Sizes
    n_X = len(model.state_vars)
    n_V2 = len(model.control_vars)
    n_V = int(n_V2/2)

    
    ## Initialise integer arrays
    if symbolic:
        Nf = sympy.zeros(n_X,n_V)
        Nr = sympy.zeros(n_X,n_V)
    else:
        Nf = np.zeros((n_X,n_V),'i')
        Nr = np.zeros((n_X,n_V),'i')
    
    ## Find the stoichiometric  matrices
    for i_species, cr in enumerate(model.constitutive_relations):
        xi = "x_"+str(i_species)
        #spec_name = model.state_vars[xi][0].name
        spec_name = getName(model,xi)
        #print(xi,':',spec_name)
        if spec_name in chemostats:
            continue

        for j, cv in enumerate(model.control_vars):
            is_f = (j % 2) ==0
            j_reac = int(j/2);
            if is_f:
                #n = -sympy.diff(cr,cv)
                n = -cr.coeff(cv)
                #print(i_species, j_reac, n)
                #Nf[i_species][j_reac] = n
                Nf[i_species,j_reac] += n
            else:
                # = -sympy.diff(cr,cv)
                n = -cr.coeff(cv)
                #print(i_species, j_reac, n)
                #Nr[i_species][j_reac] = n
                Nr[i_species,j_reac] += n

    ## Compute the stoichiometric matrix 
    N = Nr - Nf

     ## print(N)
    return N,Nf,Nr

def stoich(model,chemostats=[],linear=[],N=None,K=None,G=None,UniDir=None,symbolic=False,quiet=False):
    """Return stoichometric information from a bond-graph model.

    Parameters:
    model : BondGraphTools model -- bond graph of chemical reaction network
    chemostats : list -- list of chemostats

    See:
    https://bondgraphtools.readthedocs.io/

    Example:
    >>> s = stoich.stoich(stoich.model())
    >>> stoich.sprints(s)
    N:
    [[-1  0]
    [ 0  1]
    [ 1 -1]
    [-1  1]]
    Nf:
    [[1 0]
    [0 0]
    [0 1]
    [1 0]]
    Nr:
    [[0 0]
    [0 1]
    [1 0]
    [0 1]]
    Nfr:
    [[1 0 0 0]
    [0 0 0 1]
    [0 1 1 0]
    [1 0 0 1]]
    K:
    []
    G:
    [[ 1  1  1  0]
    [-1 -1  0  1]]
    Z:
    [[1 0 0]
    [0 0 1]
    [0 1 0]
    [1 0 1]]
    D:
    [[-1  0]
    [ 1 -1]
    [ 0  1]]
    species:
    ['A', 'B', 'C', 'E']
    reaction:
    ['r1', 'r2']

    >>> s = stoich.stoich(ABCE.model(),["A","B"])
    >>> stoich.sprints(s)
    N:
    [[ 0  0]
    [ 0  0]
    [ 1 -1]
    [-1  1]]
    Nf:
    [[0 0]
    [0 0]
    [0 1]
    [1 0]]
    Nr:
    [[0 0]
    [0 0]
    [1 0]
    [0 1]]
    Nfr:
    [[0 0 0 0]
    [0 0 0 0]
    [0 1 1 0]
    [1 0 0 1]]
    K:
    [[1]
    [1]]
    G:
    [[1 0 0 0]
    [0 1 0 0]
    [0 0 1 1]]
    Z:
    [[0 0]
    [0 0]
    [0 1]
    [1 0]]
    D:
    [[-1  1]
    [ 1 -1]]
    species:
    ['A', 'B', 'C', 'E']
    reaction:
    ['r1', 'r2']
    """
    
    ## Extract stoichiometric matrix
    if N is None:
        ## Extract stoichiometric matrix N from model
        if not quiet:
            print("Computing N ...")
        N,Nf,Nr = getStoich(model,linear=linear,chemostats=chemostats,symbolic=symbolic,quiet=quiet)
        if not quiet:
            print("Done.")
    else:
        ## Extract forward and reverse from N
        Nf = -((N<0)*N)
        Nr = (N>0)*N

    ## Number of states and flows
    n_X = N.shape[0]
    n_V = N.shape[1]

    ## Get lists of species and reactions
    species,i_spec,spec_index,i_lin,spec_par_name = get_species(model,
                                                                linear=linear)
    reaction,i_reac,reac_index,j_lin,reac_par_name = get_reactions(model,
                                                                      linear=linear)
    

    ## Compute the structure matrix
    S = np.block([[np.zeros((n_X,n_X)), N], [-N.T, np.zeros((n_V,n_V))]])

    ## Compute Nfr = [Nf Nr]
    Nfr = np.block([Nf,Nr])
    
    ## Compute the null spaces
    if K is None:
        if not quiet:
            print("Computing K ...")
        K = inull(N,integer=True,symbolic=symbolic)
        if not quiet:
            print("Done.")

    if G is None:
        if not quiet: 
            print("Computing G ...")
        G = inull(N.T,integer=True,symbolic=symbolic).T
        if not quiet:
            print("Done.")

    ## Convert to complex form
    Z,D = N2ZD(Nf,Nr,symbolic=symbolic)
    
    ## Number of complexes
    n_Z = Z.shape[1]
         
    ## Set up unidirectional reactions.
    if not UniDir is None:
        if not quiet:
            print("Set up unidirectional reactions")
        for j,reac in enumerate(reaction):
            if reac in UniDir:
                if not quiet:
                    print(f"Setting reaction {reac}({j}) to unidirectional")
                for i in range(n_X):
                    if D[i,j] > 0:
                        D[i,j] = 0

    ## Matrices to transform between full state X and reduced state x
    L_xX,L_Xx,G_X,L_dX,i_x = xX(N,G,symbolic=symbolic)
    n_x = L_xX.shape[0]

    ## Species gain parameter vector
    K_s = sympy.Matrix(sympy.symbols(spec_par_name))
    # ## Linear capacitors are parameterised with capacitance
    # for  i in i_lin:
    #     K_s[i] = 1/K_s[i]

    ## Reaction gain parameter vector
    kappa = sympy.Matrix(sympy.symbols(reac_par_name))
    # ## Linear resistors are parameterised with resistance
    # for  j in j_lin:
    #     kappa[j] = 1/kappa[j]
        
    return  {"name":model.name,
             "N":N, "Nf":Nf, "Nr":Nr, "Nfr":Nfr,
             "K":K, "G":G,
             "Z":Z, "D":D,
             "n_X":n_X, "n_x":n_x, "n_V":n_V, "n_Z":n_Z,
             "i_lin":i_lin, "j_lin":j_lin, "i_x":i_x,
             "S":S,
             "L_xX":L_xX, "L_Xx":L_Xx, "G_X":G_X, "L_dX":L_dX,
             "K_s":K_s, "kappa":kappa,
             "species":species,
             "chemostats":chemostats,
             "reaction":reaction,
             "UniDir":UniDir,
             "spec_index":spec_index,
             "reac_index":reac_index,
             "spec_par_name":spec_par_name,
             "reac_par_name":reac_par_name,
             "species_x": [species[i] for i in i_x]
    }

def statify(s,chemostats=[],flowstats=[],K=None,G=None):
    """ Apply chemostats and flowstats to s
    """
    sc = copy.deepcopy(s)       # Take a copy - leave s alone
    i_spec = sc['spec_index']
    i_reac = sc['reac_index']
    # print('i_spec:',i_spec)
    # print('i_reac:',i_reac)

    N = sc["N"]
    Nf = sc["Nf"]
    Nr = sc["Nr"]
    
    ## Set rows of N to zero at chemostats
    for stat in chemostats:
        if stat in s['species']:
            N[i_spec[stat]] = 0
            Nf[i_spec[stat]] = 0
            Nr[i_spec[stat]] = 0
        else:
            print("Chemostat",stat,"is not a model species")

    ## Set columns of N to zero at flowstats
    for stat in flowstats:
        if stat in s['reaction']:
            N[:,i_reac[stat]] = 0
            Nf[:,i_reac[stat]] = 0
            Nr[:,i_reac[stat]] = 0
        else:
            print("Flowstat",stat,"is not a model reaction")

    ## Compute the null spaces
    if K is None:
        K = inull(N,integer=True)
    if G is None:    
        G = inull(N.T,integer=True).T
    
    ## Matrices to transform between full state X and reduced state x
    L_xX,L_Xx,G_X,L_dX,i_x = xX(N,G)
    n_x = L_xX.shape[0]

    ## Compute ZD decomposition
    Z,D = N2ZD(Nf,Nr)

    sc["N"] = N
    sc["Nf"] = Nf
    sc["Nr"] = Nr
    sc["K"] = K
    sc["G"] = G
    sc["chemostats"] = chemostats
    sc["flowstats"] = flowstats
    sc["L_xX"] = L_xX
    sc["L_Xx"] = L_Xx
    sc["G_X"] = G_X
    sc["L_dX"] = L_dX
    sc["Z"] = Z
    sc["n_Z"] = Z.shape[1]
       
    sc["D"] = D
    sc["n_x"] = n_x
    sc["i_x"] = i_x
    species = s["species"]
    sc["species_x"] = [species[i] for i in i_x]
    return sc

def stoichSensitivity(s):
    """ Creates sensitivity stoichiometry from stoichiometry """
    
    species = s['species']
    reaction = s['reaction']

    ## Sensitivity species
    extra = []
    for comp in species+reaction:
        extra.append('s'+comp)

    sspecies = species + extra
    
    ## Stoichiometric matrices
    Nf = s['Nf']
    Nr = s['Nr']
    Unit = np.identity(len(reaction))
    sNf = np.vstack((Nf,Nf,Unit))
    sNr = np.vstack((Nr,Nr,Unit))
    sN = -sNf + sNr
    #print(sNf)

    ## Sizes
    n_X,n_V = sN.shape
    
    ## Indices
    spec_index = {}
    for i,spec in enumerate(sspecies):
        spec_index[spec] = i
         
    ## ZD decomposition
    sZ,sD = N2ZD(sNf,sNr)

    ## Par names
    spec_par_name = []
    for spec in sspecies:
        spec_par_name.append('K_'+spec)
         
    ## Load up the changed values
    s['N'] = sN
    s['n_X'] = n_X
    s['n_V'] = n_V
    s['Nf'] = sNf
    s['Nr'] = sNr
    s['K'] = inull(sN,integer=True)
    s['species'] = sspecies
    s['spec_index'] = spec_index
    s['reaction'] = reaction
    s['Z'] = sZ
    s['D'] = sD
    s['K_s'] = sympy.Matrix(sympy.symbols(spec_par_name))

    return extra


    
def unify(s,commonSpecies=[],commonReactions=[]):
    """ Unify species and reactions in stoichiometric matrix
    """

    
    N = s['N']
    Nf = s['Nf']
    Nr = s['Nr']
    species = s['species']
    reaction = s['reaction']
    spec_par_name = s['spec_par_name']
    #print(spec_par_name)
    
    ## Common species
    for com in commonSpecies:
        I = indices(species,com)
        i = I[0]
        J = I[1:]
        # print(com,i,J)
        ## Add up common species
        for j in J:
            N[i] += N[j]
            Nf[i] += Nf[j]
            Nr[i] += Nr[j]           

        ## Delete the redundant rows
        for j in sorted(J, reverse=True):
            N = np.delete(N,(j),0)
            Nf = np.delete(Nf,(j),0)
            Nr = np.delete(Nr,(j),0)
            del species[j]
            del spec_par_name[j]

        ## Sizes
        n_X,n_V = N.shape

        ## Indices
        spec_index = {}
        for i,spec in enumerate(species):
            spec_index[spec] = i
        
        ## ZD decomposition
        Z,D = N2ZD(Nf,Nr)
        
        ## Load up the changed values
        s['N'] = N
        s['n_X'] = n_X
        s['n_V'] = n_V
        s['Nf'] = Nf
        s['Nr'] = Nr
        s['K'] = inull(N,integer=True)
        s['species'] = species
        s['spec_index'] = spec_index
        s['reaction'] = reaction
        s['Z'] = Z
        s['D'] = D
        s['K_s'] = sympy.Matrix(sympy.symbols(spec_par_name))

def merge(s,CommonSpecies={},CommonReactions={},quiet=False):
    """ Merge common components within a BG """

    merged = list(CommonSpecies.keys())
    # print(merged)       
    for key in merged:
        if not quiet:
            print('merging',key)
        Species = []
        for spec in s['species']:
            if spec in CommonSpecies[key]:
                Species.append(key)
            else:
                Species.append(spec)
        #print(Species)
        s['species'] = Species
    
    return merged

def singleRemove(K):
    """ Remove cols of K with only one none-zero element
    """
    nz = np.count_nonzero(K,axis=0)
    i_unit = []
    for i,n in enumerate(nz):
        if n==1:
            i_unit.append(i)

    return np.delete(K,i_unit,axis=1)

def path(s,sc,removeSingle=True,reducedState=True,pathname='pr',useFR=False):
    """ 
    Pathway analysis
    Returns s structure for pathway-reduced system
    """

    sp = copy.deepcopy(s)
    ## Compute pathway N
    K = sc["K"]

    if removeSingle:             # Remove single reaction paths
        K = singleRemove(K)
    
    N = s["N"]
    Nf = s["Nf"]
    Nr = s["Nr"]
    if reducedState:
        L_dX = sc["L_dX"].astype(int)
        N_p = L_dX@N@K
        Nf_p = L_dX@Nf@K
        Nr_p = L_dX@Nr@K
    else:
        N_p = N@K
        Nf_p = Nf@K
        Nr_p = Nr@K
        
    sp["N"] = N_p

    if useFR:
        sp["Nf"] = Nf_p
        sp["Nr"] = Nr_p
    else:
        sp["Nf"] = -N_p*(N_p<0)
        sp["Nr"] =  N_p*(N_p>0)
        
    dim = sp["N"].shape
    sp["n_X"] = dim[0]
    sp["n_V"] = dim[1]

    ## Compute the null spaces
    sp["K"] = inull(N_p,integer=True)
    sp["G"] = inull(N_p.T,integer=True).T

    ## Name reactions
    reaction = []
    reac_index = {}
    for j in range(sp["n_V"]):
        name = pathname+str(j+1)
        reaction.append(name)
        reac_index[name] = j
        
    sp["reaction"] = reaction
    sp["reac_index"] = reac_index

    if reducedState:
        I_reduced = L_dX@np.arange(s["n_X"])
        species = s['species']
        spec = []
        for i_reduced  in I_reduced:
            spec.append(species[i_reduced])
        sp['species'] = spec
    else:
        sp['species'] = s['species']

    ## Compute ZD decomposition
    Z,D = N2ZD(sp['Nf'],sp['Nr'])
    sp['Z'] = Z
    sp['D'] = D

    ## Create the K_s (parameter names for species) list
    kappa = []
    for reac in sp['reaction']:
        kappa.append(f'kappa_{reac}')
    sp['kappa'] = sympy.Matrix(sympy.symbols(kappa))

    ## Create the kappa (parameter names for species) list
    K_s = []
    for spec in sp['species']:
        K_s.append(f'K_{spec}')
    sp['K_s'] = sympy.Matrix(sympy.symbols(K_s))
    
    return (sp)

def setParameter(s,parameter=None,X0=None,quiet=False):
    """ 
    Set up K,kappa, X0 and phi_0 using parameter dict 
    Default as appropriate
    """

    ## Defaults
    n_X = s["n_X"]
    n_V = s["n_V"]
    K = np.ones(n_X) 
    kappa= np.ones(n_V)
    phi0 = np.zeros(n_X)
    if X0 is None:
        X0 = np.ones(n_X)
    XX0 = copy.copy(X0)

    if parameter is not None:
        used = []                         # remember parameters which are used
        par_keys = list(parameter.keys()) # list of keys
         ## Extract parameters
        for i,par in enumerate(s["spec_par_name"]):
            if par in par_keys:
                if not quiet:
                    print("Setting",par, "to", parameter[str(par)])
                if i in s["i_lin"]:
                    K[i] = parameter[str(par)]
                else:
                    K[i] = parameter[str(par)]
                used.append(str(par))
            else:
                K[i] = 1
                
        for j,par in enumerate(s["reac_par_name"]):
            if par in par_keys:
                if not quiet:
                    print("Setting",par, "to", parameter[str(par)])
                if j in  s["j_lin"]:
                    kappa[j] = parameter[str(par)]
                else:
                    kappa[j] = parameter[str(par)]
                used.append(str(par))
            else:
                kappa[j] = 1

        phiStr = "phi0_{0}" # Template for phi parameter name
        for i,spec in enumerate(s["species"]):
            par = phiStr.format(spec)
            if par in par_keys:
                if not quiet:
                    print("Setting",par, "to", parameter[str(par)])
                phi0[i] = parameter[str(par)]
                used.append(str(par))
            else:
                phi0[i] = 0


        X0Str = "X0_{0}" # Template for X0 (initial state) parameter name
        for i,spec in enumerate(s["species"]):
            par = X0Str.format(spec)
            if par in par_keys:
                if not quiet:
                    print("Setting",par, "to", parameter[str(par)])
                XX0[i] = parameter[str(par)]
                used.append(str(par))

        unused = list(set(par_keys) - set(used))
        if len(unused)>0:
            print('Unused parameters:',unused)

    return K,kappa,phi0,XX0

def getTrans(longList,shortList):
    """ 
    Get transformation matrix converting:
    vector v_L corresponding to longList to
    vector v_S corresponding to shortList
    where all items in shortList also belong to longList
    """
    return np.eye(len(longList))[[longList.index(item) for item in shortList]]

def lin(s,sc,sf=None,model=None,x_ss=None,parameter=None,quiet=False,outvar='V',invar='X'):
    """ Linearise the system about a steady state x_ss
    """

    ## Sanity check
    valid_invar = ['X','phi']
    if invar not in valid_invar:
        print(f'invar {invar} not in {valid_invar}')
            

    ## Set up parameters
    K,kappa,phi0,X_ss = setParameter(s,parameter=parameter,X0=x_ss,quiet=quiet)
    invX_ss = np.diag(1/X_ss)

    ## Symbolic derivative of flow with respect to state dv/dx
    dvdx,dvdx0 = dflow(s,sf=sf)
    #print(dv)

    ## Create symbolic argument list
    arg = []

    ## Species constants
    species = s["species"]
    for spec in species:
        if model is None:
            par = sympy.symbols('K_'+spec)
        else:
            par = (model/spec).params['k']['value']
        arg.append(par)

    ## Reaction constants
    reaction = s["reaction"]
    for reac in reaction:
        if model is None:
            par = sympy.symbols('kappa_'+reac)
        else:
            par = (model/reac).params['r']['value']
        arg.append(par)
        
    ## Species states
    x = vec(species)
    arg += list(x)
    #print(arg)


    ## Create a numerical function: linearised system X to V
    Cfun = sympy.utilities.lambdify(arg,dvdx,"numpy")

    numArgs = tuple(K.flatten().tolist() + kappa.flatten().tolist()  + X_ss.flatten().tolist())
    #print(numArgs)
    C = Cfun(*numArgs)
    #print(C)

    ## Linearised A matrix
    N = s['N']
    A = N@C
    #print(A)

    ## Extract the transformation to reduced form
    L_xX = sc['L_xX']
    L_Xx = sc['L_Xx']
    G_X = sc['G_X']
    L_dX = sc['L_dX']

    ## Find the chemostat transformation
    n_X = sc['n_X']
    chemostats = sc["chemostats"]
    species = sc["species"]
    L_cX = getTrans(species,chemostats)

    ## Find the flowstat transformation
    n_V = s['n_V']
    N = s['N']
    if sf is None:
        flowstats = []
        N_fd = s['N']
    else:
        flowstats = sf["flowstats"]
        N_fd = sf['N']
        
    reactions = s["reaction"]
    L_fX = getTrans(reactions,flowstats)
    #L_fX = np.eye(n_V)[[reactions.index(f) for f in flowstats]]
    #print(L_fX)

    if outvar in ['V']:         # Reaction Flows
       CC = C
       n_y = n_V
    elif outvar in ['dX']:      # State flows
        CC = A
        n_y = n_X
    elif outvar in ['X']:     # Species 
        CC = np.eye(n_X)
        n_y = n_X
    elif outvar in ['phi']:     # Species potential
        # print('lin(): outvar',outvar,'is not implemented yet - using X instead')
        # CC = np.eye(n_X)
        CC = invX_ss
        n_y = n_X
    elif outvar in ['Phi']: # Reaction potential
        CC = -N.T
        n_y = n_V
    elif outvar in ['port']:
        CC = L_cX@A
        n_y = len(chemostats)
    else:
        print('lin(): outvar',outvar,'is not recognised')
        
        
    ## Create reduced form
    if invar == 'phi':
        ## Include the steady-state: dphi/dx = 1/x_ss
        L_cX = L_cX@np.diag(X_ss)
    
    a = L_xX@A@L_Xx
    b_f = L_xX@N@L_fX.T         # Flowstats
    b_c = L_xX@A@G_X@L_cX.T     # Chemostats

     #print(b_f)
    b = np.hstack((b_c,b_f))
    #print(b)
    c = CC@L_Xx
    #print(c)
    d_c =  CC@G_X@L_cX.T
    d_f = np.zeros((n_y,len(flowstats)))
    d = np.hstack((d_c,d_f))
    #print(d)


    ## Update sc structure
    updates = ["dvdx","dvdx0","A","C","a","b","c","d"]
    for update in updates:
        sc[update] = eval(update)

    ## Return linearised state-space system in control toolbox form 
    return con.ss(a,b,c,d)

    
def sim_flow0(X,K,Z,D,i_lin,j_lin,alpha,kappa,phi0,reac_index,V_flow,t,
              Kappa=None,Normalise=False):
    KK = np.diag(K)
    phi = Logn(KK@X,i_lin,Normalise=Normalise).T      # Species potentials normalised by V_N
    if phi0 is not None:
        phi += phi0/V_N(Normalise=Normalise)       # Add explicit potentials normalised by V_N
    Phi_c = Z.T@phi.T     # Complex potentials
    V0 = -D.T@np.exp(Phi_c/alpha)     # Nonlinear flows (mass-action)
    V0_lin =  -D.T@Phi_c*V_N(Normalise=Normalise)       # Linear flows
    V0[j_lin] = V0_lin[j_lin]   # Insert linear flows

    ## Vary kappa
    if Kappa is not None:
        for key, expr in Kappa.items():
            kappa[reac_index[key]] = eval(expr)           
            
    ## Flowstats
    if V_flow is not None:
        for key, expr in V_flow.items():
            V0[reac_index[key]] = eval(expr)/kappa[reac_index[key]]

    ## Actual flows
    V = np.diag(kappa)@V0

    return V,V0
    

    
def sim_fun(t,x,s,sc,X0,K,kappa,alpha=1,
            reduced=True,X_chemo=None,V_flow=None,
            Kappa=None,phi0=None,Normalise=False):

    Z = s["Z"]
    D = s["D"]
    N = sc["N"]
    i_lin = s["i_lin"]
    j_lin = s["j_lin"]
    spec_index = s['spec_index']
    reac_index = s['reac_index']
    
    if reduced:
        XX = X0
        if X_chemo is not None:
            for key, expr in X_chemo.items():
                XX[spec_index[key]] = eval(expr)
        L_xX = sc["L_xX"]
        L_Xx = sc["L_Xx"]
        G_X = sc["G_X"]
        X = L_Xx@x + G_X@XX
    else:
        X = x;

    ## Compute flows
    V,V0 = sim_flow0(X,K,Z,D,i_lin,j_lin,alpha,kappa,phi0,reac_index,V_flow,t,
                     Kappa=Kappa,Normalise=Normalise)
        
    ## Compute state derivative
    dX = N@V
    
    if reduced:
        dx = L_xX@dX
    else:
        dx = dX
        
    return dx

def sim(s,sc=None,sf=None,X0=None,t=None,linear=False,V0=None,alpha=1,parameter=None,
        X_chemo=None,V_flow=None,Kappa=None,reduced=True, Normalise=False,
        phi0=None,tol = 1e-6,quiet=True):
    
    n_X = s["n_X"]
    n_V = s["n_V"]
    i_lin = s["i_lin"]
    j_lin = s["j_lin"]
    spec_index = s['spec_index']
    reac_index = s['reac_index']
    N = s["N"]
    
    if sc is None:
        sc = s

    if sf is None:
        sf = s
        
    if X0 is None:
        X0 = np.ones(n_X)
        X0[i_lin] = 0
        #print('X0:',X0)
        
    if t is None:
        t = np.linspace(0,1)

    n_x = sc["n_x"]
    
 
    # K = np.ones(n_X) 
    # kappa= np.ones(n_V)
    # phi0 = np.zeros(n_X)
    
    # if parameter is not None:
    #     used = []                         # remember parameters which are used
    #     par_keys = list(parameter.keys()) # list of keys
    #      ## Extract parameters
    #     for i,par in enumerate(s["spec_par_name"]):
    #         if par in par_keys:
    #             if not quiet:
    #                 print("Setting",par, "to", parameter[str(par)])
    #             if i in s["i_lin"]:
    #                 K[i] = parameter[str(par)]
    #             else:
    #                 K[i] = parameter[str(par)]
    #             used.append(str(par))
    #         else:
    #             K[i] = 1
                
    #     for j,par in enumerate(s["reac_par_name"]):
    #         if par in par_keys:
    #             if not quiet:
    #                 print("Setting",par, "to", parameter[str(par)])
    #             if j in  s["j_lin"]:
    #                 kappa[j] = parameter[str(par)]
    #             else:
    #                 kappa[j] = parameter[str(par)]
    #             used.append(str(par))
    #         else:
    #             kappa[j] = 1

    #     phiStr = "phi0_{0}" # Template for phi parameter name
    #     for i,spec in enumerate(s["species"]):
    #         par = phiStr.format(spec)
    #         if par in par_keys:
    #             if not quiet:
    #                 print("Setting",par, "to", parameter[str(par)])
    #             phi0[i] = parameter[str(par)]
    #             used.append(str(par))
    #         else:
    #             phi0[i] = 0


    #     X0Str = "X0_{0}" # Template for X0 (initial state) parameter name
    #     for i,spec in enumerate(s["species"]):
    #         par = X0Str.format(spec)
    #         if par in par_keys:
    #             if not quiet:
    #                 print("Setting",par, "to", parameter[str(par)])
    #             X0[i] = parameter[str(par)]
    #             used.append(str(par))

    #     unused = list(set(par_keys) - set(used))
    #     if len(unused)>0:
    #         print('Unused parameters:',unused)
    
    if reduced:
        ## Extract transformation matrices
        L_xX = sc["L_xX"]
        L_Xx = sc["L_Xx"]
        G_X = sc["G_X"]


    ## Unit signal
    one = np.ones(t.shape)

    ## Set up parameters (and modify initial state)
    K,kappa,phi0,X0 = setParameter(s,parameter=parameter,X0=X0,quiet=quiet)

    if (n_x>0):
        if linear is False:
            
            if reduced:
                ## Create initial condition of reduced-order state
                x0 = L_xX@X0
            else:
                x0 = X0

            ## Simulate reduced-order system
            x = sci.odeint(sim_fun,x0,t,
                           atol=tol,rtol=tol,hmax=t[1]-t[0],
                           args=(sf,sc,X0,K,kappa,alpha,reduced,X_chemo,V_flow,
                                 Kappa,phi0,Normalise,),
                           tfirst=True)
        else:
            ## Linearised system in Python Control Systems Library format
            sys = lin(s,sc,x_ss=X0,parameter=parameter,quiet=quiet)

            ## Chemostat inputs
            if X_chemo is not None:
                chemostats = sc['chemostats']
                #print(chemostats)
                U = np.zeros((len(chemostats),len(t)))
                for i,chemo in enumerate(chemostats):
                    if chemo in X_chemo.keys(): 
                        U[i] = eval(X_chemo[chemo])
                                  
            t_out, yy ,xx = con.forced_response(sys,T=t,U=U,return_x=True)
            #x = (xx + L_xX@X0).T
            x = xx.T + (L_xX@X0).T
    else:
        x = 0

    if reduced:
        ## Reconstruct full state
        XX0=np.outer(G_X@X0,one)

        if X_chemo is not None:
            for key, expr in X_chemo.items():
                XX0[spec_index[key],:] = eval(expr)

        if (n_x>0):
            X = (L_Xx@x.T).T + XX0.T
        else:
            X = XX0.T
    else:
        X = x

    ## Compute potentials
    KX = np.diag(K)@X.T
    phi = V_N(Normalise=Normalise)*(Logn(KX,i_lin,Normalise=Normalise)).T + phi0
    Phi = -phi@N
    
    ## Reconstruct flows.
    if not linear:
        Z = sf["Z"]
        D = sf["D"]

        if Kappa is None:
            V,V0 = sim_flow0(X.T,K.T,Z,D,i_lin,j_lin,alpha,kappa,phi0,reac_index,V_flow,t,Kappa=Kappa)
            V = V.T

        else:
            V = []
            V0 = []
            for i,ti in enumerate(t):
                Vi,V0i = sim_flow0(X[i,:],K,Z,D,i_lin,j_lin,alpha,kappa,phi0,reac_index,V_flow,ti,Kappa=Kappa)
                V.append(Vi)
                V0.append(V0i)
            V = np.array(V)
            V0 = np.array(V0)

            
    else:
        V = yy.T
        if V0 is not None:
            V += V0

    ## Compute dX = NV
    dX = (s['N']@V.T).T
    dXc = (sc['N']@V.T).T

    ## Compute power dissipated in each Re component
    P_Re = Phi*V

    ## Compute the power associated with Cs
    P_C = phi*dX
    
    ## Results
    res = {};
    res['t'] = t
    res['X'] = X
    res['x'] = x
    res['V'] = V
    res['phi'] = phi
    res['Phi'] = Phi
    res['dX'] = dX
    res['dXc'] = dXc
    res['P_Re'] = P_Re
    res['P_C'] = P_C
    return res

def plot(s,res,plotPhi=False,plotPower=False,x_ss=None,v_ss=None,dX=False,species=None,reaction=None,x=None,xlabel=None,ylabel=None,xlim=None,ylim=None,i0=None,filename=None,lw=4):
    """ Plot results of sim()
    
    Parameter:
    s : stoichiometric information from stoich()
    res : results from sim()
    x_ss,v_ss : steady state state and flow to be subtracted
    dX: set to True to plot dX/dt=NV in place of X
    species : list of species to plot (default all)
    reaction : list of reactions to plot (default all)
    x : optional alternative x axis (1D array)
    xlim: x axis limits as (min,max)
    ylim: y axis limits as (min,max)
    i0: first data point used
    filename : plot to this filename else plot to screen
    """

    if plotPhi:
        specSym = 'phi'
        reacSym = 'Phi'
    elif plotPower:
        specSym = 'P_C'
        reacSym = 'P_Re'
    else:
        if dX:
            specSym = 'dX'
        else:
            specSym = 'X'
            
        reacSym = 'V'

    if i0 is None:
        i1 = len(res['t'])
    else:
        i1 = len(res['t'])-i0

    if x is None:
        t = copy.copy(res['t'][-i1:])
        if xlabel is None:
            xlabel = '$t$'
        if ylabel is None:
            ylabel = specSym
    else:
        t = copy.copy(x[-i1:])
        if xlabel is None:
            xlabel = '$x$'
        if ylabel is None:
            ylabel = specSym

    if species is None:
        X = copy.copy(res[specSym][-i1:,:])
        Species = s["species"]
    else:
        I = [s['spec_index'][spec] for spec in species]
        X = copy.copy(res[specSym][-i1:,I])
        if x_ss is not None:
            X = X - x_ss[I]
            specSym = '$X-X_{ss}$'
            
        Species = [s["species"][i] for i in I]   

    if reaction is None:
        V = copy.copy(res[reacSym][-i1:,:])
        Reaction = s["reaction"]  
    else:
        I = [s['reac_index'][reac] for reac in reaction]
        V = copy.copy(res[reacSym][-i1:,I])
        if v_ss is not None:
            V = V - v_ss[I]
            reacSym = '$V-V_ss$'
        Reaction = [s["reaction"][i] for i in I]

    ## Clear previous plots
    plt.clf()

    if len(Species)>0:
        if len(Reaction)>0:
            plt.subplot(211)
        if xlim is not None:
            plt.xlim(xlim)
        if ylim is not None:
            plt.ylim(ylim)
        plt.plot(t,X,lw=lw)
        plt.grid()
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.legend(Species)
        
    if len(Reaction)>0:
        if len(Species)>0:
            plt.subplot(212)
        if xlim is not None:
            plt.xlim(xlim)
        if ylim is not None:
            plt.ylim(ylim)
        plt.plot(t,V,lw=lw)
        plt.grid()
        plt.xlabel(xlabel)
        plt.ylabel(reacSym)
        plt.legend(Reaction)

    if filename is not None:
        plt.savefig(filename)
        
    plt.show()
    plt.close()

def DtoGraph(s,directed=False):
    """ Create digraph from D matrix embedded in s """

    ## Create list of complexes (nodes)
    comp = prodStoichName(s["Z"].T,s["species"])
    print(f'Complexes: {comp}')
    
    D = s["D"]
    nPath = D.shape[1]
    edges = []
    for iPath in range(nPath):
        if len(np.nonzero(D[:,iPath]>0)[0])>0:
            i_in = np.nonzero(D[:,iPath]<0)[0][0]
            i_out = np.nonzero(D[:,iPath]>0)[0][0]
            edge = (comp[i_in],comp[i_out])
            edges.append(edge)

    ## Create graph G
    if directed:
        G = nx.DiGraph()
    else:
        G = nx.Graph()
    G.add_nodes_from(comp)
    G.add_edges_from(edges)

    return G

def linkage(s):
    """ Linkage classes of network """
    
    G = DtoGraph(s,directed=False)
    all_connected_subgraphs = []

    # here we ask for all connected subgraphs that have at least 2 nodes AND have less nodes than the input graph
    for nb_nodes in range(2, G.number_of_nodes()):
        for SG in (G.subgraph(selected_nodes) for selected_nodes in itertools.combinations(G, nb_nodes)):
            if nx.is_connected(SG):
                #print(SG.nodes)
                all_connected_subgraphs.append(SG)

    ## Remove subgraphs larger ones
    linkage_classes = copy.copy(all_connected_subgraphs)
    for subgraph1 in all_connected_subgraphs:
        nodes1 = subgraph1.nodes
        for subgraph2 in all_connected_subgraphs:
            nodes2 = subgraph2.nodes
            if len(nodes2)<len(nodes1):
                if set(nodes2).issubset(set(nodes1)):
                    #print(nodes1,nodes2)
                    if subgraph2 in linkage_classes:
                        linkage_classes.remove(subgraph2)

    for lclass in linkage_classes:
        print(lclass.nodes)
        
    l = len(linkage_classes)
    print(f'{l} linkage classes')
    return l

def deficiency(s):
    """ """
    r = np.linalg.matrix_rank(s['N'])
    n = s['n_Z']
    l = linkage(s)
    d = n-l-r
    print(f'deficiency = {d} ({n}-{l}-{r})')

def draw(s):
    """ Draw the digraph of the system
    See P. Gawthrop and E. J. Crampin. 
    Bond graph representation of chemical reaction networks. 
    IEEE Transactions on NanoBioscience, 17(4):1--7, October 2018. 
    Available at arXiv:1809.00449.
    """

    G = DtoGraph(s,directed=True)

    ## Count cycles
    cycles = len(list(nx.simple_cycles(G)))
    if cycles==1:
        Cycles = " cycle"
    else:
        Cycles = " cycles"
        
    title = s["name"]+" ("+str(cycles)+Cycles+")"
    nx.draw_kamada_kawai(G,with_labels=True,font_weight='bold',
                         node_size=3000,node_color='0.7',arrowsize=50)
    plt.title(title)
    
    #print('Number of cycles =', len(list(nx.simple_cycles(G))))

def model():

    """Test bond graph model for stoich()

    Implements the enzyme-catalysed reaction:
    A+E = C = B+E

    Example:
    >>> s = stoich.stoich(stoich.model())
    >>> stoich.sprint(s,"N") # Print stoichiometric matrix
    N:
    [[-1  0]
     [ 0  1]
     [ 1 -1]
     [-1  1]]

    See also:
    stoich -- generate stoichiometric information

    See:
    P.J. Gawthrop and E.J. Crampin. 
    Bond graph representation of chemical reaction networks. 
    IEEE Transactions on NanoBioscience, 17(4):1--7, October 2018.

    """


    ## Model  ABCE
    model = bgt.new(name="ABCE")

    ## Component Ce:A
    K_A = sympy.symbols('K_A')
    RT = sympy.symbols('RT')
    A = bgt.new("Ce",name="A",value={'k':K_A,'R':RT,'T':1},library="BioChem")

    ## Component Ce:B
    K_B = sympy.symbols('K_B')
    RT = sympy.symbols('RT')
    B = bgt.new("Ce",name="B",value={'k':K_B,'R':RT,'T':1},library="BioChem")

    ## Component Ce:C
    K_C = sympy.symbols('K_C')
    RT = sympy.symbols('RT')
    C = bgt.new("Ce",name="C",value={'k':K_C,'R':RT,'T':1},library="BioChem")

    ## Component Ce:E
    K_E = sympy.symbols('K_E')
    RT = sympy.symbols('RT')
    E = bgt.new("Ce",name="E",value={'k':K_E,'R':RT,'T':1},library="BioChem")

    ## Junction 0:mtt0
    mtt0 = bgt.new("0")

    ## Junction 0:mtt0_2
    mtt0_2 = bgt.new("0")

    ## Junction 1:mtt1
    mtt1 = bgt.new("1")

    ## Junction 1:mtt1_r
    mtt1_r = bgt.new("1")

    ## Component Re:r1
    kappa_r1 = sympy.symbols('kappa_r1')
    RT = sympy.symbols('RT')
    r1 = bgt.new("Re",name="r1",value={'r':kappa_r1,'R':RT,'T':1},library="BioChem")

    ## Junction 1:mtt1_2
    mtt1_2 = bgt.new("1")

    ## Junction 1:mtt1_2_r
    mtt1_2_r = bgt.new("1")

    ## Component Re:r2
    kappa_r2 = sympy.symbols('kappa_r2')
    RT = sympy.symbols('RT')
    r2 = bgt.new("Re",name="r2",value={'r':kappa_r2,'R':RT,'T':1},library="BioChem")

    ## Component list
    components = (
      A,
      B,
      C,
      E,
      mtt0,
      mtt0_2,
      mtt1,
      mtt1_r,
      r1,
      mtt1_2,
      mtt1_2_r,
      r2
    )
    bgt.add(model, *components)

    ## Bonds
    bgt.connect(mtt1_2_r,B)
    bgt.connect(mtt0_2,C)
    bgt.connect(mtt0,E)
    bgt.connect(mtt1_2_r,mtt0)
    bgt.connect(mtt1_r,mtt0_2)
    bgt.connect(mtt0,mtt1)
    bgt.connect(A,mtt1)
    bgt.connect((r1,1),mtt1_r)
    bgt.connect(mtt1,(r1,0))
    bgt.connect(mtt0_2,mtt1_2)
    bgt.connect((r2,1),mtt1_2_r)
    bgt.connect(mtt1_2,(r2,0))

    return model

