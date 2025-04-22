.. _mitrecounter:

==========================================
MITRE Technique & Tactic Counter 
==========================================

This tool, ``tt_counter.py``, reads text files, identifies MITRE ATT&CK® technique IDs (e.g., ``T1234``), and counts their occurrences. It utilizes the `mitreattack-python <https://github.com/mitre-attack/mitreattack-python>`_ library to retrieve and display the associated tactics for each identified technique based on the official MITRE ATT&CK CTI data.

Installation
------------

**Prerequisites:**

*   Python 3 and pip
*   Network access to download dependencies and the ATT&CK CTI data.

**Steps:**

1.  **Install Python Dependencies:**
    Navigate to the directory ``scripts/MitreTTP`` containing the ``tt_counter.py`` script and the ``requirements.txt`` file. Run:

    .. code-block:: bash

       pip3 install -r requirements.txt

2.  **Download and Extract MITRE ATT&CK CTI Data:**
    The script requires the official MITRE ATT&CK Enterprise data in STIX format. Download and prepare it using the following commands:

    .. code-block:: bash

       # Download the specific ATT&CK version archive (adjust version tag if needed)
       wget https://github.com/mitre/cti/archive/refs/tags/ATT\&CK-v16.1.tar.gz

       # Extract the archive
       tar xvfz ATT\&CK-v16.1.tar.gz

       # Create a symbolic link for the default filename expected by the script
       # This links the actual JSON file to the name 'enterprise-attack.json'
       # in the current directory.
       ln -s cti-ATT\&CK-v16.1/enterprise-attack/enterprise-attack.json .

    .. note::
       The script requires the ``enterprise-attack.json`` file (or the file specified as the second argument) to be accessible from where the script is run. The symbolic link step above makes it available under the default name in the current directory.


Usage
-----

Execute the script from your terminal using Python 3:

.. code-block:: bash

   ./tt_counter.py <input_text_file> [mitre_json_file]

Arguments
---------

*   ``<input_text_file>`` (Required):
    The path to the text file you want to scan for MITRE technique IDs. This file can be any text-based format (e.g., ``.rst``, ``.md``, ``.txt``) that contains strings matching the pattern ``Txxxx`` (T followed by four digits).

*   ``[mitre_json_file]`` (Optional):
    The path to the MITRE ATT&CK Enterprise STIX JSON file. If omitted, the script defaults to looking for a file named ``enterprise-attack.json`` in the current working directory.

Output
------

The script prints the following information to standard output:

1.  For each unique technique ID found:
    *   The technique ID (e.g., ``T1590``)
    *   The number of times it occurred in the input file.
    *   A Python list containing the names of the associated MITRE ATT&CK Tactic(s).
2.  A summary line showing the total count of all technique ID occurrences found.
3.  A summary line showing the count of unique technique IDs found.

Example
-------

**Command:**

.. code-block:: bash

   ./tt_counter.py ../attackbed/docs/source/scenarios/videoserver.rst enterprise-attack.json

**Sample Output:**

.. code-block:: text

   T1590: 1 ['Reconnaissance']
   T1591: 1 ['Reconnaissance']
   T1595: 2 ['Reconnaissance']
   T1592: 1 ['Reconnaissance']
   T1594: 1 ['Reconnaissance']
   T1190: 1 ['Initial Access']
   T1059: 1 ['Execution']
   T1574: 2 ['Persistence', 'Privilege Escalation', 'Defense Evasion']
   T1104: 1 ['Command and Control']
   T1055: 1 ['Privilege Escalation', 'Defense Evasion']
   T1105: 1 ['Command and Control']
   T1087: 1 ['Discovery']
   T1083: 1 ['Discovery']
   T1201: 1 ['Discovery']
   T1069: 1 ['Discovery']
   T1057: 1 ['Discovery']
   T1518: 1 ['Discovery']
   T1082: 1 ['Discovery']
   T1614: 1 ['Discovery']
   T1016: 1 ['Discovery']
   T1049: 1 ['Discovery']
   T1033: 1 ['Discovery']
   T1007: 1 ['Discovery']
   T1615: 1 ['Discovery']
   T1068: 1 ['Privilege Escalation']
   T1546: 2 ['Persistence', 'Privilege Escalation']
   T1548: 1 ['Privilege Escalation', 'Defense Evasion']
   T1547: 1 ['Persistence', 'Privilege Escalation']
   T1053: 1 ['Execution', 'Persistence', 'Privilege Escalation']
   T1078: 1 ['Persistence', 'Privilege Escalation', 'Defense Evasion', 'Initial Access']
   T1098: 1 ['Persistence', 'Privilege Escalation']
   T1136: 1 ['Persistence']
   T1556: 1 ['Credential Access', 'Persistence', 'Defense Evasion']
   T1218: 1 ['Defense Evasion']
   T1555: 1 ['Credential Access']
   T1046: 1 ['Discovery']
   T1120: 1 ['Discovery']
   T1124: 1 ['Discovery']
   T1497: 1 ['Defense Evasion', 'Discovery']
   Summary: 42
   Unique: 39
