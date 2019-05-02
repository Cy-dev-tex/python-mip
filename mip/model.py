from typing import List, Tuple

from mip.constants import *
from math import inf
from builtins import property
from os import environ
from collections import defaultdict

class SolutionNotAvailable(Exception):
    """Exception that is raised when some method to query some
    solution property is used but no solution is available"""
    pass


class Column:
    """A column contains all the non-zero entries of a variable in the constraint matrix. 
    To create a variable see :meth:`~mip.model.model.add_var`
    """

    def __init__(self,
                 constrs: List["Constr"] = None,
                 coeffs: List[float] = None):
        self.constrs = constrs
        self.coeffs = coeffs


class Constr:
    """ A row (constraint) in the constraint matrix

        A constraint can be added to the model using the overloaded operator
        +=, e.g., if :code:`m` is a model:

        .. code:: python

          m += 3*x1 + 4*x2 <= 5

        summation expressions are also supported:

        .. code:: python

          m += xsum(x[i] for i in range(n)) == 1
    """

    def __init__(self, model: "Model", idx: int, name: str = ""):
        self.model = model
        self.idx = idx
        self.name = name  # discuss this var

    def __hash__(self) -> int:
        return self.idx

    def __str__(self) -> str:
        return self.name

    @property
    def pi(self) -> float:
        return self.model.solver.constr_get_pi(self)

    @property
    def expr(self) -> "LinExpr":
        return self.model.solver.constr_get_expr(self)

    @expr.setter
    def expr(self, value: "LinExpr") -> None:
        self.model.solver.constr_set_expr(self, value)


class LinExpr:
    """
    Linear expressions are used to enter the objective function and the model \
    constraints. These expressions are created using operators and variables.

    Consider a model object m, the objective function of :code:`m` can be specified as:
    
    .. code:: python

     m.objective = 10*x1 + 7*x4

    In the example bellow, a constraint is added to the model

    .. code:: python
    
     m += xsum(3*x[i] i in range(n)) - xsum(x[i] i in range(m))

    A constraint is just a linear expression with the addition of a sense (==,
    <= or >=) and a right hand side, e.g.:

    .. code:: python
    
     m += x1 + x2 + x3 == 1
    """

    def __init__(self,
                 variables: List["Var"] = None,
                 coeffs: List[float] = None,
                 const: float = 0,
                 sense: str = ""):
        self.const = const
        self.expr = {}
        self.sense = sense

        if variables:
            assert len(variables) == len(coeffs)
            for i in range(len(coeffs)):
                if coeffs[i] == 0:
                    continue
                self.add_var(variables[i], coeffs[i])

    def __add__(self, other) -> "LinExpr":
        result = self.copy()
        if isinstance(other, Var):
            result.add_var(other, 1)
        elif isinstance(other, LinExpr):
            result.add_expr(other)
        elif isinstance(other, (int, float)):
            result.add_const(other)
        return result

    def __radd__(self, other) -> "LinExpr":
        return self.__add__(other)

    def __iadd__(self, other) -> "LinExpr":
        if isinstance(other, Var):
            self.add_var(other, 1)
        elif isinstance(other, LinExpr):
            self.add_expr(other)
        elif isinstance(other, (int, float)):
            self.add_const(other)
        return self

    def __sub__(self, other) -> "LinExpr":
        result = self.copy()
        if isinstance(other, Var):
            result.add_var(other, -1)
        elif isinstance(other, LinExpr):
            result.add_expr(other, -1)
        elif isinstance(other, (int, float)):
            result.add_const(-other)
        return result

    def __rsub__(self, other) -> "LinExpr":
        return (-self).__add__(other)

    def __isub__(self, other) -> "LinExpr":
        if isinstance(other, Var):
            self.add_var(other, -1)
        elif isinstance(other, LinExpr):
            self.add_expr(other, -1)
        elif isinstance(other, (int, float)):
            self.add_const(-other)
        return self

    def __mul__(self, other) -> "LinExpr":
        assert isinstance(other, int) or isinstance(other, float)
        result = self.copy()
        result.const *= other
        for var in result.expr.keys():
            result.expr[var] *= other

        # if constraint sense will change
        if self.sense == GREATER_OR_EQUAL and other <= -1e-8:
            self.sense = LESS_OR_EQUAL
        if self.sense == LESS_OR_EQUAL and other <= -1e-8:
            self.sense = GREATER_OR_EQUAL

        return result

    def __rmul__(self, other) -> "LinExpr":
        return self.__mul__(other)

    def __imul__(self, other) -> "LinExpr":
        assert isinstance(other, int) or isinstance(other, float)
        self.const *= other
        for var in self.expr.keys():
            self.expr[var] *= other
        return self

    def __truediv__(self, other) -> "LinExpr":
        assert isinstance(other, int) or isinstance(other, float)
        result = self.copy()
        result.const /= other
        for var in result.expr.keys():
            result.expr[var] /= other
        return result

    def __itruediv__(self, other) -> "LinExpr":
        assert isinstance(other, int) or isinstance(other, float)
        self.const /= other
        for var in self.expr.keys():
            self.expr[var] /= other
        return self

    def __neg__(self) -> "LinExpr":
        return self.__mul__(-1)

    def __str__(self) -> str:
        result = []

        if self.expr:
            for var, coeff in self.expr.items():
                result.append("+ " if coeff >= 0 else "- ")
                result.append(str(abs(coeff)) if abs(coeff) != 1 else "")
                result.append("{var} ".format(**locals()))

        if self.sense:
            result.append(self.sense + "= ")
            result.append(str(abs(self.const)) if self.const < 0 else "- " +
                                                                      str(abs(self.const)))
        elif self.const != 0:
            result.append(
                "+ " + str(abs(self.const)) if self.const > 0 else "- " +
                                                                   str(abs(self.const)))

        return "".join(result)

    def __eq__(self, other) -> "LinExpr":
        result = self - other
        result.sense = "="
        return result

    def __le__(self, other) -> "LinExpr":
        result = self - other
        result.sense = "<"
        return result

    def __ge__(self, other) -> "LinExpr":
        result = self - other
        result.sense = ">"
        return result

    def add_const(self, const: float):
        """adds a constant value to the linear expression, in the case of a constraint
        this correspond to the right-hand-side"""
        self.const += const

    def add_expr(self, expr: "LinExpr", coeff: float = 1):
        """extends a linear expression with the contents of another"""
        self.const += expr.const * coeff
        for var, coeff_var in expr.expr.items():
            self.add_var(var, coeff_var * coeff)

    def add_term(self, expr, coeff: float = 1):
        """extends a linear expression with another multiplied by a constant value coeff"""
        if isinstance(expr, Var):
            self.add_var(expr, coeff)
        elif isinstance(expr, LinExpr):
            self.add_expr(expr, coeff)
        elif isinstance(expr, float) or isinstance(expr, int):
            self.add_const(expr)

    def add_var(self, var: "Var", coeff: float = 1):
        """adds a variable with a coefficient to the constraint"""
        if var in self.expr:
            if -EPS <= self.expr[var] + coeff <= EPS:
                del self.expr[var]
            else:
                self.expr[var] += coeff
        else:
            self.expr[var] = coeff

    def copy(self) -> "LinExpr":
        copy = LinExpr()
        copy.const = self.const
        copy.expr = self.expr.copy()
        copy.sense = self.sense
        return copy

    def equals(self:"LinExpr", other:"LinExpr") -> bool:
        """returns true if a linear expression equals to another, false otherwise"""
        if (self.const != other.const):
            return False
        if (self.sense != other.sense):
            return False
        if (len(self.expr)!=len(other.expr)):
            return False
        for i,(v,c) in enumerate(self.expr.items()):
            if v not in self.expr:
                return False
            oc = self.expr[v]
            if ( abs(c-oc)>1e-12 ):
                return False;
        return True

    def __hash__(self):
        hashEl = [v.idx for v in self.expr.keys()]
        for c in self.expr.values():
            hashEl.append(c)
        hashEl.append(self.const)
        hashEl.append(self.sense)
        return hash(tuple(hashEl))


class Model:
    """ Mixed Integer Programming Model

    This is the main class, providing methods for building, optimizing,
    querying optimization results and reoptimizing Mixed-Integer Programming
    Models.

    To check how models are created please see the examples included.

    """

    def __init__(self, name: str = "",
                 sense: str = MINIMIZE,
                 solver_name: str = ""):
        """Model constructor

        Creates a Mixed-Integer Linear Programming Model. The default model
        optimization direction is Minimization. To store and optimize the model
        the MIP package automatically searches and connects in runtime to the
        dynamic library of some MIP solver installed on your computer, nowadays
        gurobi and cbc are supported. This solver is automatically selected,
        but you can force the selection of a specific solver with the parameter
        solver_name.

        Args:
            name (str): model name
            sense (str): MINIMIZATION ("MIN") or MAXIMIZATION ("MAX")
            solver_name: gurobi or cbc, searches for which
                solver is available if not informed

        """
        # initializing variables with default values
        self.name = name
        self.solver_name = solver_name
        self.solver = None
        if "solver_name" in environ:
            solver_name = environ["solver_name"]
        if "solver_name".upper() in environ:
            solver_name = environ["solver_name".upper()]

        self.__mipStart = []

        # list of constraints and variables
        self.constrs = []
        self.constrs_by_name = {}
        self.vars = []
        self.vars_by_name = {}
        self.__cuts_generator = None

        if solver_name.upper() == GUROBI:
            from mip.gurobi import SolverGurobi
            self.solver = SolverGurobi(self, name, sense)
        elif solver_name.upper() == CBC:
            from mip.cbc import SolverCbc
            self.solver = SolverCbc(self, name, sense)
        else:
            # checking which solvers are available
            from mip import gurobi
            if gurobi.has_gurobi:
                from mip.gurobi import SolverGurobi
                self.solver = SolverGurobi(self, name, sense)
                self.solver_name = GUROBI
            else:
                from mip import cbc
                from mip.cbc import SolverCbc
                self.solver = SolverCbc(self, name, sense)
                self.solver_name = CBC

        self.sense = sense

        self.__threads = 0
        self.__status = LOADED;
        self.__cuts = 1

    def __del__(self):
        if self.solver:
            del self.solver

    def __iadd__(self, other) -> "Model":
        if isinstance(other, LinExpr):
            if len(other.sense) == 0:
                # adding objective function components
                self.objective = other
            else:
                # adding constraint
                self.add_constr(other)
        elif isinstance(other, tuple):
            if isinstance(other[0], LinExpr) and isinstance(other[1], str):
                if len(other[0].sense) == 0:
                    self.objective = other[0]
                else:
                    self.add_constr(other[0], other[1])

        return self

    def add_var(self, name: str = "",
                lb: float = 0.0,
                ub: float = INF,
                obj: float = 0.0,
                var_type: str = CONTINUOUS,
                column: "Column" = None) -> "Var":
        """ Creates a new variable in the model, returning its reference

        Args:
            name (str): variable name (optional)
            lb (float): variable lower bound, default 0.0
            ub (float): variable upper bound, default infinity
            obj (float): coefficient of this variable in the objective function, default 0
            var_type (str): CONTINUOUS ("C"), BINARY ("B") or INTEGER ("I")
            column (Column): constraints where this variable will appear, necessary \
            only when constraints are already created in the model and a new \
            variable will be created.

        Examples:

            To add a variable :code:`x` which is continuous and greater or equal to zero to model :code:`m`::

                x = m.add_var()

            The following code creates a vector of binary variables :code:`x[0], ..., x[n-1]` to model :code:`m`::

                x = [m.add_var(type=BINARY) for i in range(n)]


        """
        if var_type == BINARY:
            lb = 0.0
            ub = 1.0
        if len(name.strip()) == 0:
            nc = self.solver.num_cols()
            name = "C{:011d}".format(nc)
        idx = self.solver.add_var(obj, lb, ub, var_type, column, name)
        self.vars.append(Var(self, idx, name))
        self.vars_by_name[name] = self.vars[-1]
        return self.vars[-1]

    def add_constr(self, lin_expr: "LinExpr", name: str = "") -> Constr:
        """ Creates a new constraint (row)

        Adds a new constraint to the model

        Args:
            lin_expr (LinExpr): linear expression
            name (str): optional constraint name, used when saving model to\
            lp or mps files

        Examples:

        The following code adds the constraint :math:`x_1 + x_2 \leq 1` 
        (x1 and x2 should be created first using 
        :func:`add_var<mip.model.Model.add_var>`)::

            m += x1 + x2 <= 1

        Which is equivalent to::

            m.add_constr( x1 + x2 <= 1 )

        Summation expressions can be used also, to add the constraint \
        :math:`\displaystyle \sum_{i=0}^{n-1} x_i = y` and name this \
        constraint :code:`cons1`::

            m += xsum(x[i] for i in range(n)) == y, "cons1"

        """

        if isinstance(lin_expr, bool):
            return None  # empty constraint
        idx = self.solver.add_constr(lin_expr, name)
        self.constrs.append(Constr(self, idx, name))
        self.constrs_by_name[name] = self.constrs[-1]
        return self.constrs[-1]

    def copy(self, solver_name: str = None) -> "Model":
        """ Creates a copy of the current model

        Args:
            solver_name(str): solver name (optional)

        Returns:
            clone of current model

        """
        if not solver_name:
            solver_name = self.solver_name
        copy = Model(self.name, self.sense, solver_name)

        # adding variables
        for v in self.vars:
            copy.add_var(name=v.name, lb=v.lb, ub=v.ub, obj=v.obj, var_type=v.var_type)

        # adding constraints
        for c in self.constrs:
            expr = c.expr  # todo: make copy of constraint"s lin_expr
            copy.add_constr(lin_expr=expr, name=c.name)

        # setting objective function"s constant
        copy.objective_const = self.get_objective_const()

        return copy

    def get_constr_by_name(self, name: str) -> "Constr":
        """ Queries a constraint by its name

        Args:
            name(str): constraint name

        Returns:
            constraint
        """
        return self.constrs_by_name.get(name, None)

    @property
    def objective_bound(self) -> float:
        return self.solver.get_objective_bound()

    @property
    def objective(self) -> LinExpr:
        """The objective function of the problem as a linear expression.

        Examples:

            The following code adds all :code:`x` variables :code:`x[0], ..., x[n-1]`, to
            the objective function of model :code:`m` with the same cost :code:`w`::

                m.objective = xsum(w*x[i] for i in range(n))

            A simpler way to define the objective function is the use of the
            model operator += ::

                m += xsum(w*x[i] for i in range(n))

            Note that the only difference of adding a constraint is the lack of
            a sense and a rhs.

        """
        return self.solver.get_objective()

    @objective.setter
    def objective(self, expr):
        if isinstance(expr, int) or isinstance(expr, float):
            self.solver.set_objective(LinExpr([], [], expr))
        elif isinstance(expr, Var):
            self.solver.set_objective(LinExpr([expr], [1]))
        elif isinstance(expr, LinExpr):
            self.solver.set_objective(expr)

    @property
    def verbose(self) -> int:
        """0 to disable solver messages printed on the screen, 1 to enable
        """
        return self.solver.get_verbose()

    @verbose.setter
    def verbose(self, v : int):
        return self.solver.set_verbose(v)

    @property
    def threads(self) -> int:
        """number of threads to be used when solving the problem. 
        0 uses solver default configuration, -1 uses the number of available
        processing cores and :math:`\geq 1` uses the specified number of threads.
        An increased number of threads may improve the solution time but
        also increases the memory consumption."""
        return self.__threads

    @threads.setter
    def threads(self, th : int):
        self.__threads = th

    @property
    def sense(self) -> str:
        """ The optimization sense

        Returns:
            the objective function sense, MINIMIZE (default) or (MAXIMIZE)
        """

        return self.solver.get_objective_sense()

    @sense.setter
    def sense(self, sense: str):
        self.solver.set_objective_sense(sense)

    @property
    def objective_const(self) -> float:
        """Returns the constant part of the objective function
        """
        return self.solver.get_objective_const()

    @objective_const.setter
    def objective_const(self, const: float) -> None:
        self.solver.set_objective_const(const)

    @property
    def objective_value(self) -> float:
        """Objective function value of the solution found
        """
        return self.solver.get_objective_value()

    @property
    def num_solutions(self) -> int:
        """Number of solutions found during the MIP search

        Returns:
            number of solutions stored in the solution pool

        """
        return self.solver.get_num_solutions()

    @property
    def objective_values(self) -> List[float]:
        """List of costs of all solutions in the solution pool

        Returns:
            costs of all solutions stored in the solution pool 
            as an array from 0 (the best solution) to :attr:`~mip.model.model.num_solutions`-1.
        """
        return [float(self.solver.get_objective_value_i(i))\
                 for i in range(self.num_solutions)] 

    def get_var_by_name(self, name: str) -> "Var":
        """Searchers a variable by its name

        Returns:
            a reference to the variable
        """
        return self.vars_by_name.get(name, None)

    def relax(self):
        """ Relax integrality constraints of variables

        Changes the type of all integer and binary variables to
        continuous. Bounds are preserved.
        """
        self.solver.relax()
        for v in self.vars:
            if v.type == BINARY or v.type == INTEGER:
                v.type = CONTINUOUS

    @property
    def cuts_generator(self : "Model") -> "CutsGenerator":
        """Cut generator callback. Cut generators are called whenever a solution where one or more
        integer variables appear with continuous values. A cut generator will
        try to produce one or more inequalities to remove this fractional point.
        """
        return self.__cuts_generator

    @cuts_generator.setter
    def cuts_generator(self : "Model", cuts_generator : "CutsGenerator"):
        self.__cuts_generator = cuts_generator

    @property
    def emphasis(self) -> int:
        """defines the main objective of the search, if set to 1 (FEASIBILITY) then
        the search process will focus on try to find quickly feasible solutions and
        improving them; if set to 2 (OPTIMALITY) then the search process will try to
        find a provable optimal solution, procedures to further improve the lower bounds will
        be activated in this setting, this may increase the time to produce the first
        feasible solutions but will probably pay off in longer runs; the default option
        if 0, where a balance between optimality and feasibility is sought.
        """
        return self.solver.get_emphasis()

    @emphasis.setter
    def emphasis(self, emph: int):
        self.solver.set_emphasis(emph)

    @property
    def cuts(self) -> int:
        """controls the generation of cutting planes, 0 disables completely, 1 (default) generates
        cutting planes in a moderate way, 2 generates cutting planes aggressively and 3 generates 
        even more cutting planes. Cutting planes usually improve the LP relaxation bound but also make the 
        solution time of the LP relaxation larger, so the overall effect is hard to predict and it is
        usually a good option to try different settings for this parameter.
        """
        return self.__cuts

    @cuts.setter
    def cuts(self, cuts : int):
        if cuts<0 or cuts>3:
            print('Warning: invalid value ({}) for parameter cuts, keeping old setting.'.format(self.__cuts))
        self.__cuts = cuts

    def optimize(self,
                 max_seconds: float = inf,
                 max_nodes: int = inf,
                 max_solutions: int = inf) -> int:
        """ Optimizes current model

        Optimizes current model, optionally specifying processing limits.

        To optimize model :code:`m` within a processing time limit of 300 seconds::

            m.optimize(max_seconds=300)

        Args:
            max_seconds (float): Maximum runtime in seconds (default: inf)
            max_nodes (float): Maximum number of nodes (default: inf)
            max_solutions (float): Maximum number of solutions (default: inf)

        Returns:
            optimization status, which can be OPTIMAL(0), ERROR(-1), INFEASIBLE(1), UNBOUNDED(2). When optimizing problems
            with integer variables some additional cases may happen, FEASIBLE(3) for the case when a feasible solution was found
            but optimality was not proved, INT_INFEASIBLE(4) for the case when the lp relaxation is feasible but no feasible integer
            solution exists and NO_SOLUTION_FOUND(5) for the case when an integer solution was not found in the optimization.

        """
        if self.__threads != 0:
            self.solver.set_num_threads(self.__threads)
        #self.solver.set_callbacks(branch_selector, incumbent_updater, lazy_constrs_generator)
        self.solver.set_processing_limits(max_seconds, max_nodes, max_solutions)

        self.__status = self.solver.optimize()

        return self.__status

    def read(self, path: str):
        """Reads a MIP model in :code:`.lp` or :code:`.mps` file format.

        Args:
            path(str): file name

        """
        self.solver.read(path)
        n_cols = self.solver.num_cols()
        n_rows = self.solver.num_rows()
        for i in range(n_cols):
            self.vars.append(Var(self, i, self.solver.var_get_name(i)))
            self.vars_by_name[self.vars[-1].name] = self.vars[-1]
        for i in range(n_rows):
            self.constrs.append(Constr(self, i, self.solver.constr_get_name(i)))
            self.constrs_by_name[self.constrs[-1].name] = self.constrs[-1]
        self.sense = self.solver.get_objective_sense()

    @property
    def start(self) -> List[Tuple["Var", float]]:
        """Initial feasible solution

        Enters an initial feasible solution. Only the main binary/integer
        decision variables which appear with non-zero values in the initial
        feasible solution need to be informed. Auxiliary or continuous
        variables are automatically computed.  
        """ 
        return self.__mipStart

    @start.setter
    def start(self, start_sol: List[Tuple["Var", float]]):
        self.__mipStart = start_sol
        self.solver.set_start(start_sol)

    def write(self, path: str):
        """Saves the the MIP model, use the extension :code:`.lp` or :code:`.mps` in the file
        name to specify the file format.

        Args:
            path(str): file name
        """
        self.solver.write(path)

    @property
    def num_cols(self) -> int:
        """number of columns (variables) in the model"""
        return len(self.vars)

    @property
    def num_int(self) -> int:
        """number of integer variables in the model"""
        return self.solver.num_int()

    @property
    def num_rows(self) -> int:
        """number of rows (constraints) in the model"""
        return len(self.constrs)

    @property 
    def num_nz(self) -> int:
        """number of non-zeros in the constraint matrix"""
        return self.solver.num_nz()

    @property
    def cutoff(self) -> float:
        """upper limit for the solution cost, solutions with cost > cutoff
        will be removed from the search space, a small cutoff value may significantly
        speedup the search, but if cutoff is set to a value too low
        the model will become infeasible"""
        return self.solver.get_cutoff()

    @cutoff.setter
    def cutoff(self, value: float):
        self.solver.set_cutoff(value)

    @property
    def max_mip_gap_abs(self) -> float:
        """tolerance for the quality of the optimal solution, if a
        solution with cost :math:`c` and a lower bound :math:`l` are available and :math:`c-l<` :code:`mip_gap_abs`,
        the search will be concluded, see mip_gap to determine
        a percentage value """
        return self.solver.get_mip_gap_abs()

    @max_mip_gap_abs.setter
    def max_mip_gap_abs(self, value):
        self.solver.set_mip_gap(value)

    @property
    def max_mip_gap(self) -> float:
        """value indicating the tolerance for the maximum percentage deviation
        from the optimal solution cost, if a solution with cost :math:`c` and a lower bound :math:`l`
        are available and :math:`(c-l)/l <` :code:`max_mip_gap` the search will be concluded."""
        return self.solver.get_mip_gap()

    @max_mip_gap.setter
    def max_mip_gap(self, value):
        self.solver.set_mip_gap(value)

    @property
    def max_seconds(self) -> float:
        """time limit in seconds for search"""
        return self.solver.get_max_seconds()

    @max_seconds.setter
    def max_seconds(self, max_seconds: float):
        self.solver.set_max_seconds(max_seconds)

    @property
    def max_nodes(self) -> int:
        """maximum number of nodes to be explored in the search tree"""
        return self.solver.get_max_nodes()

    @max_nodes.setter
    def max_nodes(self, max_nodes: int):
        self.solver.set_max_nodes(max_nodes)

    @property
    def max_solutions(self) -> int:
        """solution limit, search will be stopped when :code:`max_solutions` were found"""
        return self.solver.get_max_solutions()

    @max_solutions.setter
    def max_solutions(self, max_solutions: int):
        self.solver.set_max_solutions(max_solutions)

    @property
    def status(self) -> int:
        """ optimization status, which can be OPTIMAL(0), ERROR(-1), INFEASIBLE(1), UNBOUNDED(2). When optimizing problems
            with integer variables some additional cases may happen, FEASIBLE(3) for the case when a feasible solution was found
            but optimality was not proved, INT_INFEASIBLE(4) for the case when the lp relaxation is feasible but no feasible integer
            solution exists and NO_SOLUTION_FOUND(5) for the case when an integer solution was not found in the optimization.
        """
        return self.__status


class Solver:

    def __init__(self, model: Model, name: str, sense: str):
        self.model = model
        self.name = name
        self.sense = sense

    def __del__(self): pass

    def add_var(self,
                name: str = "",
                obj: float = 0,
                lb: float = 0,
                ub: float = INF,
                var_type: str = CONTINUOUS,
                column: "Column" = None) -> int:
        if var_type == BINARY:
            lb = 0.0
            ub = 1.0

    def add_constr(self, lin_expr: "LinExpr", name: str = "") -> int: pass

    def get_objective_bound(self) -> float: pass

    def get_objective(self) -> LinExpr: pass

    def get_objective_const(self) -> float: pass

    def relax(self): pass

    def optimize(self) -> int: pass

    def get_objective_value(self) -> float: pass

    def get_objective_value_i(self, i: int) -> float: pass

    def get_num_solutions(self) -> int: pass

    def get_objective_sense(self) -> str: pass

    def set_objective_sense(self, sense: str): pass

    def set_start(self, start: List[Tuple["Var", float]]) -> None: pass

    def set_objective(self, lin_expr: "LinExpr", sense: str = "") -> None: pass

    def set_objective_const(self, const: float) -> None: pass

    def set_callbacks(self,
                      branch_selector: "BranchSelector" = None,
                      incumbent_updater: "IncumbentUpdater" = None,
                      lazy_constrs_generator: "LazyConstrsGenerator" = None) -> None:
        pass

    def set_processing_limits(self,
                              max_time: float = inf,
                              max_nodes: int = inf,
                              max_sol: int = inf):
        pass

    def get_max_seconds(self) -> float: pass

    def set_max_seconds(self, max_seconds: float): pass

    def get_max_solutions(self) -> int: pass

    def set_max_solutions(self, max_solutions: int): pass

    def get_max_nodes(self) -> int: pass

    def set_max_nodes(self, max_nodes: int): pass

    def set_num_threads(self, threads:int): pass

    def write(self, file_path: str) -> None: pass

    def read(self, file_path: str) -> None: pass

    def num_cols(self) -> int: pass

    def num_rows(self) -> int: pass

    def num_nz(self) -> int:pass

    def num_int(self) -> int:pass

    def get_emphasis(self) -> int: pass

    def set_emphasis(self, emph: int): pass

    def get_cutoff(self) -> float: pass

    def set_cutoff(self, cutoff: float): pass

    def get_mip_gap_abs(self) -> float: pass

    def set_mip_gap_abs(self, mip_gap_abs: float): pass

    def get_mip_gap(self) -> float: pass

    def set_mip_gap(self, mip_gap: float): pass

    def get_verbose(self) -> int: pass

    def set_verbose(self, verbose : int):pass

    # Constraint-related getters/setters

    def constr_get_expr(self, constr: Constr) -> LinExpr: pass

    def constr_set_expr(self, constr: Constr, value: LinExpr) -> LinExpr: pass

    def constr_get_name(self, idx: int) -> str: pass

    def constr_get_pi(self, constr: Constr) -> float: pass

    # Variable-related getters/setters

    def var_get_lb(self, var: "Var") -> float: pass

    def var_set_lb(self, var: "Var", value: float) -> None: pass

    def var_get_ub(self, var: "Var") -> float: pass

    def var_set_ub(self, var: "Var", value: float) -> None: pass

    def var_get_obj(self, var: "Var") -> float: pass

    def var_set_obj(self, var: "Var", value: float) -> None: pass

    def var_get_type(self, var: "Var") -> str: pass

    def var_set_type(self, var: "Var", value: str) -> None: pass

    def var_get_column(self, var: "Var") -> Column: pass

    def var_set_column(self, var: "Var", value: Column) -> None: pass

    def var_get_rc(self, var: "Var") -> float: pass

    def var_get_x(self, var: "Var") -> float: pass

    def var_get_xi(self, var: "Var", i: int) -> float: pass

    def var_get_name(self, idx: int) -> str: pass


class Var:
    """
    Objects of class Var are decision variables of a model. The creation
    of variables is performed calling the :meth:`~mip.model.Model.add_var`
    method of the Model class.

    """

    def __init__(self,
                 model: Model,
                 idx: int,
                 name: str = ""):
        self.model = model
        self.idx = idx
        self.name = name  # discuss this var

    def __hash__(self) -> int:
        return self.idx

    def __add__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [1, 1])
        elif isinstance(other, LinExpr):
            return other.__add__(self)
        elif isinstance(other, int) or isinstance(other, float):
            return LinExpr([self], [1], other)

    def __radd__(self, other) -> LinExpr:
        return self.__add__(other)

    def __sub__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [1, -1])
        elif isinstance(other, LinExpr):
            return (-other).__iadd__(self)
        elif isinstance(other, int) or isinstance(other, float):
            return LinExpr([self], [1], -other)

    def __rsub__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [-1, 1])
        elif isinstance(other, LinExpr):
            return other.__sub__(self)
        elif isinstance(other, int) or isinstance(other, float):
            return LinExpr([self], [-1], other)

    def __mul__(self, other) -> LinExpr:
        assert isinstance(other, int) or isinstance(other, float)
        return LinExpr([self], [other])

    def __rmul__(self, other) -> LinExpr:
        return self.__mul__(other)

    def __truediv__(self, other) -> LinExpr:
        assert isinstance(other, int) or isinstance(other, float)
        return self.__mul__(1.0 / other)

    def __neg__(self) -> LinExpr:
        return LinExpr([self], [-1.0])

    def __eq__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [1, -1], sense="=")
        elif isinstance(other, LinExpr):
            return other == self
        elif isinstance(other, int) or isinstance(other, float):
            if other != 0:
                return LinExpr([self], [1], -1 * other, sense="=")
            return LinExpr([self], [1], sense="=")

    def __le__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [1, -1], sense="<")
        elif isinstance(other, LinExpr):
            return other >= self
        elif isinstance(other, int) or isinstance(other, float):
            if other != 0:
                return LinExpr([self], [1], -1 * other, sense="<")
            return LinExpr([self], [1], sense="<")

    def __ge__(self, other) -> LinExpr:
        if isinstance(other, Var):
            return LinExpr([self, other], [1, -1], sense=">")
        elif isinstance(other, LinExpr):
            return other <= self
        elif isinstance(other, int) or isinstance(other, float):
            if other != 0:
                return LinExpr([self], [1], -1 * other, sense=">")
            return LinExpr([self], [1], sense=">")

    def __str__(self) -> str:
        return self.name

    @property
    def lb(self) -> float:
        """the variable lower bound"""
        return self.model.solver.var_get_lb(self)

    @lb.setter
    def lb(self, value: float) -> None:
        self.model.solver.var_set_lb(self, value)

    @property
    def ub(self) -> float:
        """the variable upper bound"""
        return self.model.solver.var_get_ub(self)

    @ub.setter
    def ub(self, value: float) -> None:
        self.model.solver.var_set_ub(self, value)

    @property
    def obj(self) -> float:
        """coefficient of a variable in the objective function"""
        return self.model.solver.var_get_obj(self)

    @obj.setter
    def obj(self, value: float) -> None:
        self.model.solver.var_set_obj(self, value)

    @property
    def type(self) -> str:
        """variable type ('B') BINARY, ('C') CONTINUOUS and ('I') INTEGER"""
        return self.model.solver.var_get_type(self)

    @type.setter
    def type(self, value: str):
        assert value in (BINARY, CONTINUOUS, INTEGER)
        self.model.solver.var_set_type(self, value)

    @property
    def column(self) -> Column:
        "coefficients of variable in constraints"
        return self.model.solver.var_get_column(self)

    @column.setter
    def column(self, value: Column):
        self.model.solver.var_set_column(self, value)

    @property
    def rc(self) -> float:
        "reduced cost, only available after a linear programming model (no integer variables) is optimized"
        if self.model.status != OPTIMAL:
            raise SolutionNotAvailable('Solution not available.')

        return self.model.solver.var_get_rc(self)

    @property
    def x(self) -> float:
        """solution value"""
        if self.model.status == LOADED:
            raise SolutionNotAvailable('Model was not optimized, solution not available.')
        elif self.model.status == INFEASIBLE or self.model.status==CUTOFF:
            raise SolutionNotAvailable('Infeasible model, solution not available.')
        elif self.model.status == UNBOUNDED:
            raise SolutionNotAvailable('Unbounded model, solution not available.')
        elif self.model.status == NO_SOLUTION_FOUND:
            raise SolutionNotAvailable('Solution not found during optimization.')

        return self.model.solver.var_get_x(self)

    def xi(self, i: int) -> float:
        """solution value for this variable in the :math:`i`-th solution from the solution pool"""
        if self.model.status == LOADED:
            raise SolutionNotAvailable('Model was not optimized, solution not available.')
        elif self.model.status == INFEASIBLE or self.model.status==CUTOFF:
            raise SolutionNotAvailable('Infeasible model, solution not available.')
        elif self.model.status == UNBOUNDED:
            raise SolutionNotAvailable('Unbounded model, solution not available.')
        elif self.model.status == NO_SOLUTION_FOUND:
            raise SolutionNotAvailable('Solution not found during optimization.')

        return self.model.solver.var_get_xi(self, i)


class CutsGenerator:
    """abstract class for implementing cut generators"""
    def __init__(self, model: Model):
        self.model = model

    def generate_cuts(self, relax_solution: List[Tuple[Var, float]]) -> List[LinExpr]:
        """Method called by the solve engine to generate cuts

           After analyzing the contents of the fractional solution in :code:`relax_solution`, one 
           or mode cuts (:class:`~mip.model.LinExpr`) may be generated and returned. These cuts are added to the
           relaxed model.

        Args:
            relax_solution(List[Tuple[Var, float]]): a list of tuples (variable,value) indicating the values of variables in the current fractional solution. Variables at zero are not included.

        Note: take care not to query the value of the fractional solution in the cut generation method using the :code:`x`
        methods from original references to problem variables, use the contents of :code:`relax_solution` instead.
        """
        raise NotImplementedError()


class CutPool:
    def __init__(self : "CutPool"):
        """Stores a list list of different cuts, repeated cuts are discarded.
        """
        self.__cuts = []

        # positions for each hash code to speedup 
        # the search of repeated cuts
        self.__pos = defaultdict( list )

    def add(self : "CutPool", cut : "LinExpr") -> bool:
        """tries to add a cut to the pool, returns true if this is a new cut, false if it is a repeated one

        Args:
            cut(LinExpr): a constraint
        """
        hcode = hash(cut)
        l = self.__pos[hcode]
        for p in l:
            if self.__cuts[p].equals(cut):
                return False

        self.__pos[hcode].append(len(self.__cuts))
        self.__cuts.append(cut)

        return True

    @property
    def cuts(self : "CutPool") -> List["LinExpr"]:
        return self.__cuts


class BranchSelector:
    def __init__(self, model: Model):
        self.model = model

    def select_branch(self, relax_solution: List[Tuple[Var, float]]) -> Tuple[Var, int]:
        raise NotImplementedError()


class IncumbentUpdater:
    def __init__(self, model: Model):
        self.model = model

    def update_incumbent(self, solution: List[Tuple[Var, float]]) -> List[Tuple[Var, float]]:
        raise NotImplementedError()


class LazyConstrsGenerator:
    def __init(self, model: Model):
        self.model = model

    def generate_lazy_constrs(self, solution: List[Tuple[Var, float]]) -> List[LinExpr]:
        raise NotImplementedError()


def xsum(terms) -> LinExpr:
    result = LinExpr()
    for term in terms:
        result.add_term(term)
    return result


# function aliases
quicksum = xsum


def read_custom_settings() -> str:
    global customCbcLib
    from pathlib import Path
    home = str(Path.home())
    import os
    configpath = os.path.join(home, ".config")
    if os.path.isdir(configpath):
        conffile = os.path.join(configpath, "python-mip")
        if os.path.isfile(conffile):
            f = open(conffile, "r")
            for line in f:
                if "=" in line:
                    cols = line.split("=")
                    if cols[0].strip().lower() == "cbc-library":
                        customCbcLib = cols[1].lstrip().rstrip().replace('"', "")


print("Using Python-MIP package version {}".format(VERSION))
customCbcLib = ""
read_custom_settings()
# print("customCbcLib {}".format(customCbcLib))

# vim: ts=4 sw=4 et
