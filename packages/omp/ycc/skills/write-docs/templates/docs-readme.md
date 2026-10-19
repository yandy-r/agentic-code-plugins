# {{PROJECT_NAME}} Documentation

Welcome to the {{PROJECT_NAME}} documentation.

## Quick Links

{{#if HAS_ARCHITECTURE}}

- [Architecture Overview](architecture/overview.md)
  {{/if}}
  {{#if HAS_API}}
- [API Reference](api/README.md)
  {{/if}}
  {{#if HAS_FEATURES}}
- [Feature Guides](features/README.md)
  {{/if}}
  {{#if HAS_DEVELOPMENT}}
- [Developer Guide](development/README.md)
  {{/if}}

## Documentation Map

{{NAVIGATION_TREE}}

## Recently Updated

{{#each RECENT_FILES}}

- [{{this.title}}]({{this.path}}) - _{{this.date}}_
  {{/each}}

---

_Last updated: {{GENERATED_DATE}}_
