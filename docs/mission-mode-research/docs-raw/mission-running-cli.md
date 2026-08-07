# Running in the CLI

Once a plan is approved, Droid enters Mission Control. Monitor progress, unblock workers, and redirect the orchestrator from the terminal.

## Working with Mission Control

Once the plan is approved, Droid enters Mission Control, the orchestration view that manages execution. From here you can track progress across features and milestones, see which agents are working on what, and intervene when things need adjustment.

<Tip>
  Prefer a visual dashboard? The Factory App provides a richer Mission Control experience. See [Running in the Factory App](/missions/running-app).
</Tip>

## Intervening and redirecting

Missions are not fire-and-forget. The orchestrator is an agent, and you can talk to it. The most effective way to use Missions is to treat yourself as the project manager: monitor progress, unblock workers, and redirect when the plan needs to change.

When something goes wrong (the mission freezes, a worker or milestone gets stuck, or you need to change direction), pause the orchestrator and tell it what you are seeing. See [Troubleshooting](/missions/overview#troubleshooting) for common scenarios and example prompts.

## A new kind of debugging

The skillset for working with Missions looks less like traditional debugging and more like **project management of agents**. You are not stepping through code line by line. You are monitoring a team of workers, unblocking them when they get stuck, redirecting them when priorities change, and making judgment calls about when to push through versus when to re-plan.

This is a meaningfully different way of working with AI. The core skill is knowing when and how to intervene, not writing the code yourself.

<RelatedLinks>
  <RelatedLink href='/droid-exec/overview' title='Droid Exec (Headless)'>
    Run missions non-interactively in CI or scheduled environments.
  </RelatedLink>
  <RelatedLink href='/missions/running-app' title='Running in the Factory App'>
    Use the visual Mission Control dashboard for richer monitoring.
  </RelatedLink>
</RelatedLinks>
