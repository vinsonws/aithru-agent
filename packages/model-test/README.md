# @aithru/model-test

Deterministic test model adapters for Aithru Agent.

Use this package to test agent runtime behavior without calling a real LLM provider.

## Provides

- `ScriptedModelAdapter`
- `createStaticFinalModel`
- `createStaticStructuredModel`

## Purpose

This package makes it possible to verify:

- event streaming;
- structured output;
- tool-call proposals;
- final output handling;
- runtime behavior independent from model quality.
