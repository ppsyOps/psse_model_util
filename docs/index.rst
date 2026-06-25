psse_model_util documentation
==============================

``psse_model_util`` is a Python library for reading, editing, validating, and
comparing PSS/E power system models (RAW ``v33``/``v34``/``v35`` and RAWX
formats).

It parses RAW and RAWX files into structured Python objects backed by pandas
``DataFrame`` tables and a NetworkX graph. Its primary use case is comparing
seasonal Bulk Electric System (BES) model variants (for example, summer versus
winter) at both the tabular and the topological level.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   api/index

Getting started
---------------

Load a model and inspect its network sections:

.. code-block:: python

   from psse_model_util.model import Model

   model = Model("path/to/model.raw", name="Summer_Peak")

   buses = model.network.bus           # pandas DataFrame
   lines = model.network.acline        # pandas DataFrame
   gens = model.network.generator      # pandas DataFrame

Compare two models:

.. code-block:: python

   from psse_model_util.model import Model
   from psse_model_util.compare import ModelComparison

   m1 = Model("summer.raw", name="Summer").filter_by_area(areas=[101, 102])
   m2 = Model("winter.raw", name="Winter").filter_by_area(areas=[101, 102])

   comp = ModelComparison(m1, m2)
   comp.compare_network_dfs()   # DataFrame-level column deltas
   comp.compare_graph()         # Topology: added/removed edges, path changes

See the :doc:`api/index` for the full reference, and the project ``README.md``
for installation, the quick-start guide, and the release process.

Indices and tables
-------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
