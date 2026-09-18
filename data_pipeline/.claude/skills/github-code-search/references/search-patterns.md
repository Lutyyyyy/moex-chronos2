# Advanced GitHub Search Patterns

## GitHub Web Search Queries

### Code-Specific Searches

Use `site:github.com` with WebSearch for broad discovery:

```
site:github.com "goldberg polyhedron" python
site:github.com "telegram bot" "get phone number" python
site:github.com "3d viewer" "rotate" "scale" react three.js
site:github.com "websocket client" rust async
```

### GitHub Code Search (via web)

GitHub's built-in code search supports qualifiers:

```
# By language
language:python geodesic sphere
language:typescript telegram client phone

# By path
path:src "calculate coordinates" language:python

# By repo quality
stars:>100 language:rust websocket client

# By file extension
path:*.py "goldberg" "icosahedron"
path:*.ts "telegram" "resolvePhone"

# Combined
language:python stars:>50 "geodesic" "coordinates"
```

### Package Registry Searches

Before searching raw code, check if maintained packages exist:

```
# npm
site:npmjs.com <package-description>
# PyPI
site:pypi.org <package-description>
# crates.io
site:crates.io <package-description>
# Go packages
site:pkg.go.dev <package-description>
```

## Query Construction Strategies

### Strategy 1: Algorithm Search
For mathematical/algorithmic tasks:
1. Search for the algorithm name + language: `"dijkstra" "shortest path" python`
2. Search for the domain + technique: `"geodesic sphere" "subdivision" python`
3. Search awesome lists: `awesome-<domain> github`

### Strategy 2: Integration Search
For API/service integrations:
1. Search for official SDK/client: `"<service> SDK" <language>`
2. Search for specific operation: `"<service>" "<operation>" example <language>`
3. Search for community wrappers: `"<service> client" <language> github`

### Strategy 3: UI Component Search
For UI/visual components:
1. Search component registries: `"<framework> <component>" npm/pypi`
2. Search for demos: `"<component>" demo <framework> github`
3. Search for specific interaction: `"<interaction>" "<framework>" component`

### Strategy 4: Data Format Search
For parsers/generators:
1. Search for format libraries: `"<format> parser" <language>`
2. Search for specific operations: `"<format>" "read" OR "write" OR "parse" <language>`
3. Check awesome lists: `awesome-<format>`

## Evaluating Results

### Quality Signals (Positive)
- Recent commits (within last 6 months)
- Multiple contributors
- Stars > 50 (for libraries), > 10 (for examples)
- Has tests
- Has CI/CD badges
- Clear documentation/README
- Permissive license (MIT, Apache-2.0, BSD)

### Warning Signals
- No commits for 2+ years
- No tests
- Single contributor with no activity
- GPL/AGPL license (may conflict with project requirements)
- No README or documentation
- Pinned to very old dependency versions

## Reading Code from GitHub

### Raw File URLs
To fetch actual source code, construct raw URLs:
```
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>
```

Example:
```
https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/jsm/controls/OrbitControls.js
```

### Repository API
For repository metadata:
```
https://api.github.com/repos/<owner>/<repo>
https://api.github.com/search/repositories?q=<query>
```

### Gist Search
For small snippets:
```
site:gist.github.com <query>
```

## Common Task Patterns

### Geometric/Math Algorithms
```
"<algorithm-name>" implementation <language>
"<shape>" "coordinates" OR "vertices" <language>
computational geometry <specific-task> <language>
```

### Messaging/Chat Integrations
```
"<platform>" "bot" OR "client" <language>
"<platform> API" "<specific-endpoint>" <language>
"<platform>" "<specific-feature>" example
```

### 3D Graphics
```
"<3d-library>" "<operation>" example
"<3d-library>" viewer OR renderer <framework>
WebGL OR three.js "<component-type>"
```

### File Format Processing
```
"<format>" parser OR reader <language>
"<format>" generator OR writer <language>
"<format>" "<specific-operation>" <language>
```
