One Truth, Two Representations.md

Project: [[GDDP]]
Concept: Detect divergence when the same logical node state is represented in multiple files
File: status_reconciler.rs
Time: ~35 minutes

project.yaml says:
    node-3 = Ready
nodes/node-3.yaml says:
    node-3 = Running
The validator must NOT decide:
    "close enough"
It must report:
    Diverged

Today’s principle:

Duplicated state is not trustworthy
just because both representations are individually valid.
Agreement is itself an invariant.

Keep AI closed until the critique section.

1. Coding Drill — Compare Two Authorities

Implement compare_status() manually.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Status {
    Pending,
    Ready,
    Running,
    Complete,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Consistency {
    Agrees(Status),
    Diverged {
        index: Status,
        detail: Status,
    },
}
fn compare_status(
    index: Status,
    detail: Status,
) -> Consistency {
    // TODO
    todo!()
}
fn main() {
    assert_eq!(
        compare_status(
            Status::Ready,
            Status::Ready,
        ),
        Consistency::Agrees(
            Status::Ready,
        ),
    );
    assert_eq!(
        compare_status(
            Status::Ready,
            Status::Running,
        ),
        Consistency::Diverged {
            index: Status::Ready,
            detail: Status::Running,
        },
    );
    println!(
        "status comparison passed"
    );
}

Run:

rustc status_reconciler.rs \
  && ./status_reconciler

Before compiling, answer manually:

Why return Consistency instead of bool?
Why preserve BOTH conflicting values?
What information would Result<(), ()> lose?
What is the time complexity of compare_status()?
Is either source treated as authoritative yet?

Required behavior:

same status
    -> Agrees(status)
different status
    -> Diverged {
         index,
         detail,
       }

Do not introduce filesystem parsing yet.

⸻

2. Manual Implementation — Validate a Whole Node

Now add:

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Status {
    Pending,
    Ready,
    Running,
    Complete,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ProjectEntry {
    id: &'static str,
    status: Status,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct NodeFile {
    id: &'static str,
    status: Status,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ValidationError {
    IdMismatch {
        project_id: &'static str,
        node_id: &'static str,
    },
    StatusMismatch {
        project: Status,
        node: Status,
    },
}
fn validate_pair(
    project: ProjectEntry,
    node: NodeFile,
) -> Result<(), ValidationError> {
    // TODO
    todo!()
}

Required policy:

different IDs
    -> IdMismatch
same ID
+ different statuses
    -> StatusMismatch
same ID
+ same status
    -> Ok(())

Important ordering:

validate identity
BEFORE
comparing state

Write these assertions yourself:

node-1 / Ready
node-1 / Ready
    -> Ok
node-1 / Ready
node-1 / Running
    -> StatusMismatch
node-1 / Ready
node-7 / Ready
    -> IdMismatch

Then answer:

Why check identity first?
What bug could occur if two unrelated records both say Ready?
Does valid YAML imply valid system state?
What does this validator prove that a YAML parser does not?

⸻

3. Runnable Standalone Validator

Replace the file with:

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Status {
    Pending,
    Ready,
    Running,
    Complete,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ProjectEntry {
    id: &'static str,
    status: Status,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct NodeFile {
    id: &'static str,
    status: Status,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ValidationError {
    IdMismatch {
        project_id: &'static str,
        node_id: &'static str,
    },
    StatusMismatch {
        node_id: &'static str,
        project: Status,
        node: Status,
    },
}
fn validate_pair(
    project: ProjectEntry,
    node: NodeFile,
) -> Result<(), ValidationError> {
    if project.id != node.id {
        return Err(
            ValidationError::IdMismatch {
                project_id: project.id,
                node_id: node.id,
            },
        );
    }
    if project.status != node.status {
        return Err(
            ValidationError::StatusMismatch {
                node_id: project.id,
                project: project.status,
                node: node.status,
            },
        );
    }
    Ok(())
}
fn validate_all(
    projects: &[ProjectEntry],
    nodes: &[NodeFile],
) -> Vec<ValidationError> {
    let mut errors = Vec::new();
    for project in projects {
        let matching_node = nodes
            .iter()
            .find(|node| {
                node.id == project.id
            });
        match matching_node {
            Some(node) => {
                if let Err(error) =
                    validate_pair(
                        *project,
                        *node,
                    )
                {
                    errors.push(error);
                }
            }
            None => {
                // Missing-node validation comes
                // in the modification challenge.
            }
        }
    }
    errors
}
fn main() {
    let projects = [
        ProjectEntry {
            id: "node-1",
            status: Status::Complete,
        },
        ProjectEntry {
            id: "node-2",
            status: Status::Ready,
        },
        ProjectEntry {
            id: "node-3",
            status: Status::Running,
        },
    ];
    let nodes = [
        NodeFile {
            id: "node-1",
            status: Status::Complete,
        },
        NodeFile {
            id: "node-2",
            status: Status::Running,
        },
        NodeFile {
            id: "node-3",
            status: Status::Running,
        },
    ];
    let errors = validate_all(
        &projects,
        &nodes,
    );
    assert_eq!(
        errors,
        vec![
            ValidationError::StatusMismatch {
                node_id: "node-2",
                project: Status::Ready,
                node: Status::Running,
            },
        ],
    );
    assert_eq!(
        validate_pair(
            ProjectEntry {
                id: "node-7",
                status: Status::Ready,
            },
            NodeFile {
                id: "node-8",
                status: Status::Ready,
            },
        ),
        Err(
            ValidationError::IdMismatch {
                project_id: "node-7",
                node_id: "node-8",
            }
        ),
    );
    println!(
        "cross-file validation passed"
    );
}

Run:

rustc status_reconciler.rs \
  && ./status_reconciler

Expected:

cross-file validation passed

⸻

4. Trace the Reliability Boundary

Given:

project.yaml:
node-2:
    status: ready

and:

nodes/node-2.yaml:
status: running

Fill in manually:

Project representation:
Node-file representation:
Are both individually valid values?
Do they agree?
Can the system safely report "green"?
Which invariant failed?
What exact evidence should the validator emit?

Now answer:

1. Why is schema validity insufficient?
2. Why is status disagreement a system-level failure?
3. Does disagreement tell you which source is correct?
4. Why should the validator avoid silently repairing it?
5. What is the difference between detection and reconciliation?
6. Why is “pick one source and continue” dangerous?
7. What information should an operator receive before deciding which side is stale?
8. If an AI agent updated one file but not the other, what exactly did it violate?

Compress the distinction:

Parsing answers:
    __________________________
Validation answers:
    __________________________
Reconciliation answers:
    __________________________

⸻

5. Manual Rebuild — No Reference

Close the completed program.

Rebuild from memory:

enum Status
struct ProjectEntry
struct NodeFile
enum ValidationError
fn validate_pair(...)
fn validate_all(...)

Write fresh assertions for:

same ID
same status
    -> valid
same ID
different status
    -> StatusMismatch
different ID
same status
    -> IdMismatch
three records
one mismatch
    -> exactly one error
three records
zero mismatches
    -> zero errors

Then answer without reopening the reference:

Which function validates one relationship?
Which function performs collection traversal?
Which layer knows about system invariants?
Which layer merely stores values?
Why should the validator collect errors
instead of stopping on the first mismatch?

Interview drill:

What is the complexity of validate_all()
as currently written?
Why?
What data structure could improve lookup?
What would the expected complexity become?
What tradeoff would that introduce?

⸻

6. Modification Challenge — Missing and Extra Nodes

The current validator has a hole.

This passes silently:

project.yaml contains:
    node-1
    node-2
    node-3
nodes/ contains:
    node-1
    node-2

Extend:

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ValidationError {
    IdMismatch {
        project_id: &'static str,
        node_id: &'static str,
    },
    StatusMismatch {
        node_id: &'static str,
        project: Status,
        node: Status,
    },
    MissingNodeFile {
        node_id: &'static str,
    },
    MissingProjectEntry {
        node_id: &'static str,
    },
}

Modify:

fn validate_all(
    projects: &[ProjectEntry],
    nodes: &[NodeFile],
) -> Vec<ValidationError> {
    // # to be implemented
}

Required behavior:

project entry exists
node file missing
    -> MissingNodeFile
node file exists
project entry missing
    -> MissingProjectEntry
both exist
same status
    -> no error
both exist
different status
    -> StatusMismatch

Prove:

projects:
    node-1
    node-2
nodes:
    node-1
    node-3

produces exactly:

MissingNodeFile {
    node_id: "node-2",
}
MissingProjectEntry {
    node_id: "node-3",
}

Then answer:

Why must validation run in BOTH directions?
Why is project -> nodes traversal alone incomplete?
What invariant are MissingNodeFile
and MissingProjectEntry expressing?
Would automatically creating the missing record
belong inside validation?
Why or why not?

⸻

7. Reliability Extension — Green Means More Than Agreement

Now reason about this scenario:

project status:
    Complete
node-file status:
    Complete
job:
    failed
evaluator:
    no passing receipt

The two status authorities agree.

Yet the system still should not be green.

Do not code this entire extension.

Instead design the types manually:

enum JobState {
    // TODO
}
enum EvaluationState {
    // TODO
}
struct NodeEvidence {
    // TODO
}

Then sketch:

fn validate_completion(
    status: Status,
    evidence: NodeEvidence,
) -> Result<(), ValidationError> {
    // TODO
}

Required invariant:

Status::Complete
requires:
successful execution evidence
AND
passing evaluation evidence

Answer:

What is the difference between
representation agreement
and
truth agreement?
Can two stale files agree with each other?
Why?
What independent evidence prevents that?
What does "green" need to mean
for the validator to be useful?

This is the important jump today:

project.yaml == node.yaml

does not necessarily imply:

system reality == Complete

⸻

8. Project Reflection — Trace One Real GDDP Node

Choose one node that has recently moved through execution.

Trace it manually:

Node ID:
project.yaml status:
nodes/<id>.yaml status:
Do they agree?
Job record:
Job terminal state:
Evaluator run:
Evaluator verdict:
Does "Complete" have supporting execution evidence?
Does "Complete" have supporting evaluator evidence?
Which file was written first?
Which code path writes project.yaml?
Which code path writes node YAML?
Are those writes performed by one operation
or separate operations?
What happens if the process dies between them?
AI-created state mutation traced manually:

Reflection questions:

1. How many mutable representations of node status currently exist?
2. Which code paths write each representation?
3. Can one write succeed while another fails?
4. Is there one function that owns the whole state transition?
5. If both representations say Complete, what external evidence verifies that claim?
6. Can evaluator history contradict the files?
7. Can job history contradict them?
8. Should the validator report every contradiction in one pass?
9. Which AI-generated “update status” helper would you refuse to trust until tracing every write it performs?

⸻

9. Narrow AI Critique

Use only:

Review only the cross-representation consistency
and completion-evidence invariants in this Rust validator.
Do not rewrite the program.
Do not propose a broader orchestration architecture.
Return exactly:
1. one state divergence this validator still fails to detect,
2. one missing regression assertion,
3. one Rust type or API change that would make it harder
   for two mutable status representations to drift.
Treat these as separate concepts:
- schema validity
- identity consistency
- status consistency
- execution evidence
- evaluator evidence
- reconciliation
Do not recommend automatically choosing one source
when two sources disagree.

Apply nothing until you can state exactly which invariant each suggestion protects.

⸻

Interview Compression

I built a validator for denormalized workflow state where the same logical node can appear in multiple representations. I treated cross-file agreement as an explicit invariant rather than assuming individually valid files imply valid system state. The validator reports identity mismatches, status divergence, missing counterparts, and eventually checks claimed completion against independent execution and evaluation evidence. I also keep validation separate from reconciliation: detecting that two authorities disagree is deterministic, while deciding which representation is stale is a different operation. The broader reliability principle is that duplicated state needs explicit consistency checks, and even agreement between duplicates is insufficient if external evidence contradicts them.
