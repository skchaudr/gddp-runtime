GDDP owns the execution graph, not the project’s knowledge. Nodes identify bounded work; the project provides the context required to perform it. Agents traverse the graph by entering the project, discovering relevant context, executing the task, and producing evidence.

GDDP node should contain:
├── task identity
├── dependency relationships
├── bounded objective
├── acceptance criteria
└── evidence requirements

GDDP node should NOT become:
├── project encyclopedia
├── architecture dump
├── duplicated documentation
├── giant context packet
└── substitute for repository legibility

If a node requires a giant packet to be executable, first ask whether the missing information actually belongs in <project>.

Let agents traverse the graph, not make the graph control the traversal of agents 

Example GDDP Run of Nodes:
A → B → C
   "B is ready."

Agent:
enters B
→ reads project map
→ enters relevant room
→ gathers context
→ performs work
→ produces evidence
→ exits

GDDP:
"Evidence passes. C is ready."
