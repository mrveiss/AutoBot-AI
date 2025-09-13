# SCIP (Source Code Intelligence Protocol) Official Standards

*This document contains only the official SCIP standards as defined by Sourcegraph, without any project-specific implementations.*

## Overview

SCIP (pronounced "skip") is a language-agnostic protocol for indexing source code to power code navigation functionality such as Go to definition, Find references, and Find implementations. It is a recursive acronym that stands for "SCIP Code Intelligence Protocol."

**Official Repository**: https://github.com/sourcegraph/scip

## Core Design Principles (Official)

### Primary Goals
1. **Support code navigation at IDE-level fidelity** - Provide excellent code navigation experience
2. **Make indexer creation easy** by:
   - Enabling cross-repository navigation
   - Supporting file-level incremental indexing
   - Facilitating parallel indexing
   - Supporting multi-language indexer development

### Design Philosophy
> "SCIP is meant to be a transmission format for sending data from some producers to some consumers -- it is not meant as a storage format for querying."

### Technical Design Decisions
1. **Protobuf Schema**
   - Relatively compact binary format
   - Supports easy code generation
   - Enables streaming reads/writes
   - Maintains forward/backward compatibility

2. **String-based Identifiers**
   - Prefer human-readable string IDs for symbols
   - Avoid integer ID mapping tables
   - Improve debuggability
   - Limit potential bug impact

3. **Data Encoding Approach**
   - Avoid direct graph encoding
   - Use document and array-based approaches
   - Enable streaming capabilities
   - Minimize memory consumption during indexing

### Non-Goals
- Not focused on code modification tools
- Not optimizing for consumer-side tooling
- Not prioritizing uncompressed data compactness
- Not serving as a standalone query engine

## Protocol Buffer Schema (Official)

### Main Message Types

```protobuf
syntax = "proto3";
package scip;

message Index {
  Metadata metadata = 1;
  repeated Document documents = 2;
  repeated SymbolInformation external_symbols = 3;
}

message Metadata {
  ProtocolVersion version = 1;
  ToolInfo tool_info = 2;
  string project_root = 3;
  TextEncoding text_encoding = 4;
}

message Document {
  string language = 4;
  string relative_path = 1;
  repeated Occurrence occurrences = 2;
  repeated SymbolInformation symbols = 3;
  string text = 5;
}

message Symbol {
  string scheme = 1;
  Package package = 2;
  repeated Descriptor descriptors = 3;
}

message SymbolInformation {
  string symbol = 1;
  repeated string documentation = 3;
  repeated Relationship relationships = 4;
  SymbolKind kind = 5;
  string display_name = 6;
  Signature signature_documentation = 7;
  repeated string enclosing_symbol = 8;
}

message Occurrence {
  Range range = 1;
  string symbol = 2;
  int32 symbol_roles = 3;
  repeated Diagnostic override_documentation = 4;
  SyntaxKind syntax_kind = 5;
}

message Range {
  repeated int32 start = 1;  // [line, column]
  repeated int32 end = 2;    // [line, column]
}
```

## Official Symbol Format Specification

### Symbol Grammar (Official)
```
<symbol> ::= <scheme> ' ' <package> ' ' (<descriptor>)+ | 'local ' <local-id>
<package> ::= <manager> ' ' <package-name> ' ' <version>
<scheme> ::= UTF-8 string (escape spaces with double space)
<descriptor> ::= <namespace> | <type> | <term> | <method> | <type-parameter> | <parameter> | <meta> | <macro>
```

### Symbol Components

**Scheme**: Identifies the symbol's origin/context
- UTF-8 string
- Escape spaces with double space

**Package**: Includes manager, name, and version
- Manager: Package manager identifier
- Package name: Unique package identifier
- Version: Package version

**Descriptors**: Represent nested/hierarchical symbol structure
- Form a fully qualified name
- Support various symbol types

**Local Symbols**: Only for entities within a single Document
- Format: `local <local-id>`
- Used for file-scoped symbols

### Encoding Rules (Official)
- Descriptors form a fully qualified name
- Local symbols are only for entities within a single Document
- Symbols must uniquely identify an entity across a package
- Supports escaping special characters in identifiers

## Enumerations (Official)

### ProtocolVersion
```protobuf
enum ProtocolVersion {
  UnspecifiedProtocolVersion = 0;
}
```

### TextEncoding
```protobuf
enum TextEncoding {
  UnspecifiedTextEncoding = 0;
  UTF8 = 1;
  UTF16 = 2;
}
```

### SymbolRole
```protobuf
enum SymbolRole {
  UnspecifiedSymbolRole = 0;
  Definition = 1;
  Import = 2;
  WriteAccess = 4;
  ReadAccess = 8;
  Generated = 16;
  Test = 32;
}
```

### SymbolKind
```protobuf
enum SymbolKind {
  UnspecifiedSymbolKind = 0;
  Array = 1;
  Boolean = 2;
  Class = 3;
  Constant = 4;
  Constructor = 5;
  Enum = 6;
  EnumMember = 7;
  Event = 8;
  Field = 9;
  File = 10;
  Function = 11;
  Interface = 12;
  Key = 13;
  Method = 14;
  Module = 15;
  Namespace = 16;
  Null = 17;
  Number = 18;
  Object = 19;
  Operator = 20;
  Package = 21;
  Property = 22;
  String = 23;
  Struct = 24;
  TypeParameter = 25;
  Variable = 26;
  Macro = 27;
}
```

### SyntaxKind
```protobuf
enum SyntaxKind {
  UnspecifiedSyntaxKind = 0;
  Comment = 1;
  PunctuationDelimiter = 2;
  PunctuationBracket = 3;
  Keyword = 4;
  // ... (additional syntax kinds)
  IdentifierKeyword = 13;
  IdentifierOperator = 14;
  IdentifierBuiltin = 15;
  IdentifierNull = 16;
  IdentifierConstant = 17;
  IdentifierMutableGlobal = 18;
  IdentifierParameter = 19;
  IdentifierLocal = 20;
  IdentifierShadowed = 21;
  IdentifierNamespace = 22;
  IdentifierFunction = 23;
  IdentifierFunctionDefinition = 24;
  IdentifierMacro = 25;
  IdentifierMacroDefinition = 26;
  IdentifierType = 27;
  IdentifierBuiltinType = 28;
  IdentifierAttribute = 29;
}
```

## Official Position and Range Specification

### Coordinate System
- **Line numbers**: 0-indexed
- **Column numbers**: 0-indexed character positions
- **UTF-8/UTF-16 aware**: Proper Unicode handling

### Range Format
```protobuf
message Range {
  repeated int32 start = 1;  // [line, column]
  repeated int32 end = 2;    // [line, column]
}
```

### Requirements
- Start position must be <= end position
- Ranges must be within document boundaries
- Character-level precision required

## Official Language Support

### Currently Supported (Official Implementations)
- **TypeScript/JavaScript**: scip-typescript
- **Java**: scip-java (also supports Scala, Kotlin)
- **Python**: In development

### Language Bindings Available
- **Rich bindings**: Go, Rust
- **Auto-generated bindings**: TypeScript, Haskell
- **CLI tools**: scip CLI for index manipulation

## Performance Characteristics (Official Claims)

### Compared to LSIF
- **10x speedup** in CI environments
- **4x smaller** compressed payload size
- **Better streaming**: Enables processing without loading entire index
- **Lower memory usage**: Document-based processing

### Design Benefits
- Static typing from Protobuf schema
- More ergonomic debugging
- Reduced runtime errors
- Smaller index files

## Official Tools and Ecosystem

### SCIP CLI
- Index manipulation and conversion
- LSIF compatibility support
- Debugging and inspection tools

### Official Indexers
- **scip-typescript**: `npm install -g @sourcegraph/scip-typescript`
- **scip-java**: Available as Docker image, Java launcher, fat jar

### Integration Support
- GitLab Code Intelligence (via LSIF conversion)
- Sourcegraph native support
- VS Code extensions (community)

## Standards Compliance Requirements

### For SCIP Index Producers
1. Must generate valid Protocol Buffer format
2. Must follow symbol ID format specification
3. Must provide accurate position information
4. Should support streaming output
5. Must handle UTF-8/UTF-16 encoding correctly

### For SCIP Index Consumers
1. Must handle streaming input
2. Should support all standard symbol kinds
3. Must respect symbol role classifications
4. Should provide graceful error handling
5. Must support position range validation

## Official Documentation Sources

### Primary Sources
- **Main Repository**: https://github.com/sourcegraph/scip
- **Protocol Schema**: https://github.com/sourcegraph/scip/blob/main/scip.proto
- **Design Document**: https://github.com/sourcegraph/scip/blob/main/DESIGN.md
- **Announcement Blog**: https://sourcegraph.com/blog/announcing-scip

### Language-Specific Documentation
- **Java**: https://github.com/sourcegraph/scip-java
- **TypeScript**: https://github.com/sourcegraph/scip-typescript

### Community Resources
- **Bindings**: Available for Go, Rust, TypeScript, Haskell
- **Examples**: Implementation examples in official repositories
- **Issues**: Bug reports and feature requests on GitHub

---

*This document contains only official SCIP standards as defined by Sourcegraph.*
*Last updated: 2025-01-14*
*SCIP Version: Compatible with official v0.3.x specification*
*Source: Official Sourcegraph SCIP repositories and documentation*