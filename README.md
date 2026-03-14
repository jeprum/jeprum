# Jeprum

**Live control room for AI agents - route, monitor, and govern AI agents before they cost you money or break things.**

---

## The Problem

As AI agents proliferate across enterprise workflows, teams are flying blind. There's no unified layer to answer basic operational questions:

- Which agents are running, and what are they doing?
- How much is each agent call actually costing?
- Why did an agent produce that output - and can we reproduce it?
- Are agents operating within the boundaries we set?

Today, every team building with agents is duct-taping together logging, cost tracking, and access controls. The result: runaway costs, opaque failures, and zero governance - until something breaks in production.

## What Jeprum Is

Jeprum is infrastructure that AI agents operate *through*, not a monitoring layer bolted on top.

Think of it as a control plane - the same way Kubernetes orchestrates containers or Envoy manages service mesh traffic, Jeprum sits in the agent execution path to provide:

- **Routing & Orchestration** - Direct agent traffic through policy-aware pathways
- **Cost Controls** - Set budgets, track spend per agent/task/team, kill runaway calls before they drain your API bill
- **Observability** - Full trace of agent decisions, tool calls, and outputs with reproducible debugging
- **Governance & Policy Enforcement** - Define what agents can and cannot do, enforced at the infrastructure layer

## Architecture Direction

We're currently evaluating the right enforcement layer - the core design question is where Jeprum intercepts agent execution:

| Approach | Tradeoff |
|---|---|
| **SDK-level integration** | Deep control, tighter coupling |
| **Proxy / Gateway** | Adoption-friendly, protocol-agnostic |
| **Protocol-native hooks (MCP, A2A)** | Standards-aligned, dependent on ecosystem adoption |

The answer likely involves a combination. We're studying the emerging agent protocol landscape (MCP, A2A) to make this decision well rather than fast.

## Why Now

- Agent frameworks (LangChain, CrewAI, AutoGen) are shipping fast - but none own the control layer
- Enterprises are moving agents into production without operational infrastructure
- Agent-to-agent communication protocols (MCP, A2A) are creating a standards window where the right infrastructure gets locked in early
- The cost of *not* governing agents compounds - every month without controls is budget risk and compliance exposure

## Current Stage

🔧 **Pre-build** - Architecture design and protocol research phase. Actively evaluating technical approaches before writing code that locks in the wrong abstraction.

## Background

Built by [Jithendra Puppala](https://linkedin.com/in/jithendra-siddartha), MS CS @ NYU (2027), previously Data Scientist at Reliance Jio building production ML systems serving 450M+ users.

## Get in Touch

- **Email:** jithendra.mail.me@gmail.com
- **LinkedIn:** [linkedin.com/in/jithendra-siddartha](https://linkedin.com/in/jithendra-siddartha)
