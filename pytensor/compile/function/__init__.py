import logging
import re
import traceback as tb
from collections.abc import Iterable
from pathlib import Path

import pytensor.misc.pkl_utils
from pytensor.compile.function.pfunc import pfunc
from pytensor.compile.function.types import orig_function
from pytensor.compile.mode import Mode
from pytensor.compile.profiling import ProfileStats
from pytensor.graph import Variable


__all__ = ["types", "pfunc"]

__docformat__ = "restructuredtext en"
_logger = logging.getLogger("pytensor.compile.function")


def function_dump(
    filename: str | Path,
    inputs: Iterable[Variable],
    outputs: Variable | Iterable[Variable] | dict[str, Variable] | None = None,
    mode: str | Mode | None = None,
    updates: Iterable[tuple[Variable, Variable]]
    | dict[Variable, Variable]
    | None = None,
    givens: Iterable[tuple[Variable, Variable]]
    | dict[Variable, Variable]
    | None = None,
    no_default_updates: bool = False,
    accept_inplace: bool = False,
    name: str | None = None,
    rebuild_strict: bool = True,
    allow_input_downcast: bool | None = None,
    profile: bool | ProfileStats | None = None,
    on_unused_input: str | None = None,
    extra_tag_to_remove: str | None = None,
    trust_input: bool = False,
):
    """
    This is helpful to make a reproducible case for problems during PyTensor
    compilation.

    Ex:

    replace `pytensor.function(...)` by
    `pytensor.function_dump('filename.pkl', ...)`.

    If you see this, you were probably asked to use this function to
    help debug a particular case during the compilation of an PyTensor
    function. `function_dump` allows you to easily reproduce your
    compilation without generating any code. It pickles all the objects and
    parameters needed to reproduce a call to `pytensor.function()`. This
    includes shared variables and their values. If you do not want
    that, you can choose to replace shared variables values with zeros by
    calling set_value(...) on them before calling `function_dump`.

    To load such a dump and do the compilation:

    >>> import pickle
    >>> import pytensor
    >>> d = pickle.load(open("func_dump.bin", "rb"))  # doctest: +SKIP
    >>> f = pytensor.function(**d)  # doctest: +SKIP

    Note:
    The parameter `extra_tag_to_remove` is passed to the StripPickler used.
    To pickle graph made by Blocks, it must be:
    `['annotations', 'replacement_of', 'aggregation_scheme', 'roles']`

    """
    d = {
        "inputs": inputs,
        "outputs": outputs,
        "mode": mode,
        "updates": updates,
        "givens": givens,
        "no_default_updates": no_default_updates,
        "accept_inplace": accept_inplace,
        "name": name,
        "rebuild_strict": rebuild_strict,
        "allow_input_downcast": allow_input_downcast,
        "profile": profile,
        "on_unused_input": on_unused_input,
        "trust_input": trust_input,
    }
    with Path(filename).open("wb") as f:
        pickler = pytensor.misc.pkl_utils.StripPickler(
            f, protocol=-1, extra_tag_to_remove=extra_tag_to_remove
        )
        pickler.dump(d)


def function(
    inputs: Iterable[Variable],
    outputs: Variable | Iterable[Variable] | dict[str, Variable] | None = None,
    mode: str | Mode | None = None,
    updates: Iterable[tuple[Variable, Variable]]
    | dict[Variable, Variable]
    | None = None,
    givens: Iterable[tuple[Variable, Variable]]
    | dict[Variable, Variable]
    | None = None,
    no_default_updates: bool = False,
    accept_inplace: bool = False,
    name: str | None = None,
    rebuild_strict: bool = True,
    allow_input_downcast: bool | None = None,
    profile: bool | ProfileStats | None = None,
    on_unused_input: str | None = None,
    trust_input: bool = False,
):
    """
    Return a :class:`callable object <pytensor.compile.function.types.Function>`
    that will calculate `outputs` from `inputs`.

    Parameters
    ----------
    inputs : list of either Variable or In instances.
        Function parameters, these are not allowed to be shared variables.
    outputs : list or dict of Variables or Out instances.
        If it is a dict, the keys must be strings. Expressions to compute.
    mode : string or `Mode` instance.
        Compilation mode.
    updates : iterable over pairs (shared_variable, new_expression). List, tuple
              or dict.
        Updates the values for SharedVariable inputs according to these
        expressions.
    givens : iterable over pairs (Var1, Var2) of Variables. List, tuple or dict.
             The Var1 and Var2 in each pair must have the same Type.
        Specific substitutions to make in the computation graph (Var2 replaces
        Var1).
    no_default_updates: either bool or list of Variables
        If True, do not perform any automatic update on Variables. If False
        (default), perform them all. Else, perform automatic updates on all
        Variables that are neither in "updates" nor in "no_default_updates".
    accept_inplace : bool
        True iff the graph can contain inplace operations prior to the
        optimization phase (default is False). *Note* this parameter is unsupported,
        and its use is not recommended.
    name : str
        An optional name for this function. The profile mode will print the time
        spent in this function.
    rebuild_strict : bool
        True (Default) is the safer and better tested setting, in which case
        `givens` must substitute new variables with the same Type as the
        variables they replace.
        False is a you-better-know-what-you-are-doing setting, that permits
        `givens` to replace variables with new variables of any Type.
        The consequence of changing a Type is that all results depending on that
        variable may have a different Type too (the graph is rebuilt from inputs
        to outputs). If one of the new types does not make sense for one of the
        Ops in the graph, an Exception will be raised.
    allow_input_downcast: bool or None
        True means that the values passed as inputs when calling the function
        can be silently down-casted to fit the dtype of the corresponding
        Variable, which may lose precision. False means that it will only be
        cast to a more general, or precise, type. None (default) is almost like
        False, but allows down-casting of Python float scalars to floatX.
    profile: None, True, or ProfileStats instance
        Accumulate profiling information into a given ProfileStats instance.
        If argument is `True` then a new ProfileStats instance will be used.
        If argument is a string, a new ProfileStats instance will be created
        with that string as its ``message`` attribute.
        This profiling object will be available via self.profile.
    on_unused_input
        What to do if a variable in the 'inputs' list is not used in the graph.
        Possible values are 'raise', 'warn', 'ignore' and None.
    trust_input: bool, default False
        If True, no input validation checks are performed when the function is
        called. This includes checking the number of inputs, their types and
        that multiple inputs are not aliased to each other. Failure to meet any
        of these conditions can lead to computational errors or to the
        interpreter crashing.

    Returns
    -------
    :class:`pytensor.compile.function.types.Function` instance
        A callable object that will compute the outputs (given the inputs) and
        update the implicit function arguments according to the `updates`.

    Notes
    -----
    Regarding givens: Be careful to make sure that these
    substitutions are independent--behaviour when Var1 of one pair
    appears in the graph leading to Var2 in another expression is
    undefined.  Replacements specified with givens are different
    from optimizations in that Var2 is not expected to be
    equivalent to Var1.


    Internal documentation:

        What happens when you call pytensor.function?
           1. RemoveShared: shared variables are just an abstraction to make
        things more convenient for the user. The shared variables are
        transformed into implicit inputs and implicit outputs. The
        optimizations don't see which variables are shared or not.
           2. FunctionGraph: determines whether a graph is valid. For example,
        suppose
        you merge the two apply nodes in our example above, ie, do the
        addition and the tanh at the same time. If you propose a merge that
        changes the resulting dtype or broadcastable pattern of V4, the fgraph
        will detect this.
                    inplace optimizations: say we have an apply node that
        does + on V1 and V2, with output V3. We can change the output to be
        V1, to use less memory. pytensor must be told that this optimization is
        happening though, so that other parts of the graph are given the
        correct (pre + or post + ) version of V1.
                  fgraph will raise an error if any of these types of
        modifications causes an error
                  fgraph also adds a field called "clients" to all variables.
        clients is a list of apply nodes that use the variable. this makes it
        possible to traverse the graph in both directions. this is useful for
        determining whether to do some optimizations. for example, a fusion
        operation that removes V3 is not very helpful if V3 is also needed for
        some other apply node. fusion operations result in a composite op that
        takes a minigraph of pytensor scalars and uses this to do elemwise
        operations on pytensor tensors
         3. Optimization
               How well do optimizations apply to new ops?
                 Usually there are no optimizations for new ops. In fact, new
        ops can disrupt patterns and break currently working optimizations.
        Since the Print op, for example, is not known by any optimization,
        setting a Print op in the middle of a pattern that is usually
        optimized out will block the optimization. for example, log(1+x)
        optimizes to log1p(x) but log(1+Print(x)) is unaffected by
        optimizations.
                 One exception is elemwise ops. If you implement your new op
        as a scalar op then it will automatically work with all the elemwise
        fusion machinery.

                 Local optimizations try to replace some node in the graph
        with a different node. In the case of log(1+x), we want to replace the
        log node.

                 def opt_log1p(node):
                    if not isinstance(node.op,Elemwise):
                       return
                    if not isinstance(node.op.scalar_op, log):
                       return
                    inp = node.inputs[0]
                    if inp.owner is None:
                       return
                    if not isinstance(inp.owner.op, add):
                       return
                    inp2 = inp.owner.inputs
                    check that this has length 2, and that one of the inputs
        is 1. assign the other input to x
                    return log1p(x)


         4. Linker
               The linker uses a Python loop to execute the code associated
               with all the Apply nodes in the graph in the correct order.
               The C Virtual Machine (CVM) is a linker that replaces this
               Python loop with a C loop to avoid continuously changing
               between Python and C. The CVM is faster for 2 reasons:
                 1) Its internal logic is in C, so no Python interpreter
                    overhead.
                 2) It makes native calls from the VM logic into thunks that
                    have been compiled using the CLinker.
               The VM is a linker that was developed to prototype the CVM. it
        was easier to develop the VM in Python then translate it to C instead
        of just writing it in C from scratch.

    """
    if isinstance(outputs, dict):
        assert all(isinstance(k, str) for k in outputs)

        output_keys = sorted(outputs)
        outputs = [outputs[key] for key in output_keys]

    else:
        output_keys = None

    if name is None:
        # Determine possible file names
        source_file = re.sub(r"\.pyc?", ".py", __file__)
        compiled_file = source_file + "c"

        stack = tb.extract_stack()
        idx = len(stack) - 1

        last_frame = stack[idx]
        if last_frame[0] == source_file or last_frame[0] == compiled_file:
            func_frame = stack[idx - 1]
            while "pytensor/graph" in func_frame[0] and idx > 0:
                idx -= 1
                # This can happen if we call var.eval()
                func_frame = stack[idx - 1]
            name = func_frame[0] + ":" + str(func_frame[1])

    if updates is None:
        updates = []

    if givens is None:
        givens = []
    if not isinstance(inputs, list | tuple):
        raise Exception(
            "Input variables of an PyTensor function should be "
            "contained in a list, even when there is a single "
            "input."
        )

    # compute some features of the arguments:
    uses_tuple = any(isinstance(i, list | tuple) for i in inputs)
    uses_updates = bool(updates)
    uses_givens = bool(givens)

    if uses_tuple:
        # we must use old semantics in this case.
        if profile:
            raise NotImplementedError("profiling not supported in old-style function")
        if uses_updates or uses_givens:
            raise NotImplementedError(
                "In() instances and tuple inputs trigger the old "
                "semantics, which disallow using updates and givens"
            )
        fn = orig_function(
            inputs,
            outputs,
            mode=mode,
            accept_inplace=accept_inplace,
            name=name,
            trust_input=trust_input,
        )
    else:
        # note: pfunc will also call orig_function -- orig_function is
        #      a choke point that all compilation must pass through
        fn = pfunc(
            params=inputs,
            outputs=outputs,
            mode=mode,
            updates=updates,
            givens=givens,
            no_default_updates=no_default_updates,
            accept_inplace=accept_inplace,
            name=name,
            rebuild_strict=rebuild_strict,
            allow_input_downcast=allow_input_downcast,
            on_unused_input=on_unused_input,
            profile=profile,
            output_keys=output_keys,
            trust_input=trust_input,
        )
    return fn
