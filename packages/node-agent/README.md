# @aithru/node-agent

Workflow node integration surface for Aithru Agent.

The package name is `node-agent` because these are workflow nodes that call the Agent runtime. They are not the Agent runtime itself.

## Planned nodes

- `agent.classify`
- `agent.task`

## Boundary

- Formal workflow graph belongs to `aithru-core`.
- Intelligent execution belongs to `aithru-agent`.
- This package bridges them.

The first version exports stable node type constants and config/output types. Real NodeDefinition factories will be added after the parent workspace is wired with `aithru-core` public packages.
