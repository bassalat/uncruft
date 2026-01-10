"""Cleanup category definitions for uncruft."""

from uncruft.models import Category, RiskLevel

# All cleanup categories with their metadata
CATEGORIES: dict[str, Category] = {
    # =============================================================================
    # SAFE CATEGORIES - No data loss, auto-recoverable
    # =============================================================================
    "conda_cache": Category(
        id="conda_cache",
        name="Conda Package Cache",
        paths=[
            "~/miniconda3/pkgs",
            "~/anaconda3/pkgs",
            "~/opt/miniconda3/pkgs",
            "~/opt/anaconda3/pkgs",
            "~/.conda/pkgs",
        ],
        risk_level=RiskLevel.SAFE,
        description="Cached conda package tarballs from previous installs",
        consequences="Packages will re-download on next install (slower first time)",
        recovery="Automatic - conda re-downloads packages when needed",
        cleanup_command="conda clean --all --yes",
    ),
    "npm_cache": Category(
        id="npm_cache",
        name="NPM Cache",
        paths=["~/.npm/_cacache", "~/.npm/_logs"],
        risk_level=RiskLevel.SAFE,
        description="Cached npm packages and logs",
        consequences="Packages will re-download on next npm install",
        recovery="Automatic - npm re-downloads packages when needed",
        cleanup_command="npm cache clean --force",
    ),
    "yarn_cache": Category(
        id="yarn_cache",
        name="Yarn Cache",
        paths=["~/.yarn/cache", "~/Library/Caches/Yarn"],
        risk_level=RiskLevel.SAFE,
        description="Cached yarn packages",
        consequences="Packages will re-download on next yarn install",
        recovery="Automatic - yarn re-downloads packages when needed",
        cleanup_command="yarn cache clean",
    ),
    "pip_cache": Category(
        id="pip_cache",
        name="Pip Cache",
        paths=["~/Library/Caches/pip", "~/.cache/pip"],
        risk_level=RiskLevel.SAFE,
        description="Cached pip packages",
        consequences="Packages will re-download on next pip install",
        recovery="Automatic - pip re-downloads packages when needed",
        cleanup_command="pip cache purge",
    ),
    "homebrew_cache": Category(
        id="homebrew_cache",
        name="Homebrew Cache",
        paths=["~/Library/Caches/Homebrew", "/usr/local/Caskroom/.cache"],
        risk_level=RiskLevel.SAFE,
        description="Downloaded homebrew packages and casks",
        consequences="Packages will re-download on next brew install",
        recovery="Automatic - brew re-downloads packages when needed",
        cleanup_command="brew cleanup --prune=all",
    ),
    "chrome_cache": Category(
        id="chrome_cache",
        name="Chrome Cache",
        paths=[
            "~/Library/Caches/Google/Chrome",
            "~/Library/Application Support/Google/Chrome/Default/Cache",
            "~/Library/Application Support/Google/Chrome/Default/Code Cache",
        ],
        risk_level=RiskLevel.SAFE,
        description="Chrome browser cache (not passwords or bookmarks)",
        consequences="Websites will load slower on first visit",
        recovery="Automatic - Chrome re-caches as you browse",
    ),
    "safari_cache": Category(
        id="safari_cache",
        name="Safari Cache",
        paths=[
            "~/Library/Caches/com.apple.Safari",
            "~/Library/Caches/com.apple.Safari.SafeBrowsing",
        ],
        risk_level=RiskLevel.SAFE,
        description="Safari browser cache",
        consequences="Websites will load slower on first visit",
        recovery="Automatic - Safari re-caches as you browse",
    ),
    "edge_cache": Category(
        id="edge_cache",
        name="Microsoft Edge Cache",
        paths=[
            "~/Library/Caches/com.microsoft.Edge",
            "~/Library/Application Support/Microsoft Edge/Default/Cache",
        ],
        risk_level=RiskLevel.SAFE,
        description="Microsoft Edge browser cache",
        consequences="Websites will load slower on first visit",
        recovery="Automatic - Edge re-caches as you browse",
    ),
    "firefox_cache": Category(
        id="firefox_cache",
        name="Firefox Cache",
        paths=["~/Library/Caches/Firefox"],
        risk_level=RiskLevel.SAFE,
        description="Firefox browser cache",
        consequences="Websites will load slower on first visit",
        recovery="Automatic - Firefox re-caches as you browse",
    ),
    "xcode_derived_data": Category(
        id="xcode_derived_data",
        name="Xcode DerivedData",
        paths=["~/Library/Developer/Xcode/DerivedData"],
        risk_level=RiskLevel.SAFE,
        description="Xcode build artifacts and indexes",
        consequences="Next build will be slower (full rebuild required)",
        recovery="Automatic - Xcode rebuilds on next compile",
    ),
    "xcode_archives": Category(
        id="xcode_archives",
        name="Xcode Archives",
        paths=["~/Library/Developer/Xcode/Archives"],
        risk_level=RiskLevel.REVIEW,
        description="Archived app builds for App Store submission",
        consequences="Cannot re-submit old builds without rebuilding",
        recovery="Rebuild from source code",
    ),
    "system_logs": Category(
        id="system_logs",
        name="System Logs",
        paths=["~/Library/Logs", "/var/log"],
        risk_level=RiskLevel.SAFE,
        description="Application and system log files",
        consequences="Historical logs will be unavailable for debugging",
        recovery="New logs are created automatically",
    ),
    "application_caches": Category(
        id="application_caches",
        name="Application Caches",
        paths=["~/Library/Caches"],
        risk_level=RiskLevel.SAFE,
        description="General application cache files",
        consequences="Apps may be slower on first launch",
        recovery="Automatic - Apps re-create caches as needed",
    ),
    "trash": Category(
        id="trash",
        name="Trash",
        paths=["~/.Trash"],
        risk_level=RiskLevel.REVIEW,  # REVIEW because emptying is permanent
        description="Files in the Trash",
        consequences="Deleted files cannot be recovered",
        recovery="Not recoverable after emptying - check contents before deleting",
    ),
    # =============================================================================
    # REVIEW CATEGORIES - Need user judgment
    # =============================================================================
    "docker_data": Category(
        id="docker_data",
        name="Docker Data",
        paths=["~/Library/Containers/com.docker.docker/Data/vms"],
        risk_level=RiskLevel.REVIEW,
        description="Docker images, containers, and volumes",
        consequences="Need to re-pull images and rebuild containers",
        recovery="Re-pull images with docker pull",
        cleanup_command="docker system prune -a",
    ),
    "huggingface_cache": Category(
        id="huggingface_cache",
        name="HuggingFace Models",
        paths=["~/.cache/huggingface"],
        risk_level=RiskLevel.REVIEW,
        description="Downloaded ML models from HuggingFace",
        consequences="Models will re-download when needed (can be slow/large)",
        recovery="Automatic - models re-download on use",
    ),
    "downloads_old": Category(
        id="downloads_old",
        name="Downloads (Old Files)",
        paths=["~/Downloads"],
        risk_level=RiskLevel.REVIEW,
        description="Files in Downloads folder older than 30 days",
        consequences="Files will be permanently deleted",
        recovery="Not recoverable - check before deleting",
    ),
    "ios_backups": Category(
        id="ios_backups",
        name="iOS Backups",
        paths=["~/Library/Application Support/MobileSync/Backup"],
        risk_level=RiskLevel.REVIEW,
        description="iPhone and iPad backups",
        consequences="Cannot restore devices from these backups",
        recovery="Create new backup from device",
    ),
    "xcode_simulators": Category(
        id="xcode_simulators",
        name="Xcode Simulators",
        paths=["~/Library/Developer/CoreSimulator/Devices"],
        risk_level=RiskLevel.REVIEW,
        description="iOS/watchOS/tvOS simulator data",
        consequences="Simulator data and apps will be lost",
        recovery="Re-download simulators via Xcode",
        cleanup_command="xcrun simctl delete unavailable",
    ),
    "slack_cache": Category(
        id="slack_cache",
        name="Slack Cache",
        paths=[
            "~/Library/Application Support/Slack/Cache",
            "~/Library/Application Support/Slack/Service Worker/CacheStorage",
        ],
        risk_level=RiskLevel.SAFE,
        description="Slack message and file cache",
        consequences="Slack may reload messages from server",
        recovery="Automatic - Slack re-downloads as needed",
    ),
    "spotify_cache": Category(
        id="spotify_cache",
        name="Spotify Cache",
        paths=["~/Library/Caches/com.spotify.client"],
        risk_level=RiskLevel.SAFE,
        description="Spotify music cache",
        consequences="Downloaded songs will need to re-download",
        recovery="Automatic - Spotify re-downloads as you listen",
    ),
    "vscode_cache": Category(
        id="vscode_cache",
        name="VS Code Cache",
        paths=[
            "~/Library/Application Support/Code/Cache",
            "~/Library/Application Support/Code/CachedData",
            "~/Library/Application Support/Code/CachedExtensions",
        ],
        risk_level=RiskLevel.SAFE,
        description="VS Code editor cache",
        consequences="Extensions may reload slower",
        recovery="Automatic - VS Code re-caches as needed",
    ),
    "gradle_cache": Category(
        id="gradle_cache",
        name="Gradle Cache",
        paths=["~/.gradle/caches"],
        risk_level=RiskLevel.SAFE,
        description="Gradle build cache for Java/Android projects",
        consequences="Next build will re-download dependencies",
        recovery="Automatic - Gradle re-downloads on build",
    ),
    "maven_cache": Category(
        id="maven_cache",
        name="Maven Cache",
        paths=["~/.m2/repository"],
        risk_level=RiskLevel.SAFE,
        description="Maven repository cache for Java projects",
        consequences="Dependencies will re-download on next build",
        recovery="Automatic - Maven re-downloads on build",
    ),
    "cocoapods_cache": Category(
        id="cocoapods_cache",
        name="CocoaPods Cache",
        paths=["~/Library/Caches/CocoaPods"],
        risk_level=RiskLevel.SAFE,
        description="CocoaPods dependency cache for iOS projects",
        consequences="Pods will re-download on next install",
        recovery="Automatic - pod install re-downloads",
        cleanup_command="pod cache clean --all",
    ),
    # =============================================================================
    # DEVELOPER CATEGORIES - Recursive discovery for dev artifacts
    # =============================================================================
    "node_modules": Category(
        id="node_modules",
        name="Node Modules",
        paths=[],  # Uses recursive scanning instead
        glob_patterns=["**/node_modules"],
        search_roots=["~/Documents", "~/Code", "~/Projects", "~/Developer", "~/repos", "~/src"],
        is_recursive=True,
        min_size_bytes=10 * 1024 * 1024,  # 10MB minimum
        risk_level=RiskLevel.SAFE,
        description="Node.js dependency directories",
        consequences="Run 'npm install' to restore",
        recovery="npm install or yarn install",
        # Rich knowledge base content
        what_is_it=(
            "node_modules is where npm (Node Package Manager) stores all the JavaScript packages "
            "your project depends on. Unlike other package managers, npm installs a separate copy "
            "for EACH project - so if you have 10 Node projects, you have 10 copies of React, "
            "10 copies of lodash, etc. This is intentional for isolation but causes massive disk usage. "
            "A typical React project has 200-500MB of node_modules. A complex project can exceed 1-2GB."
        ),
        why_safe=(
            "Everything in node_modules is downloaded from the npm registry. Your package.json lists "
            "what you need, and package-lock.json (or yarn.lock) records exact versions. Running "
            "'npm install' recreates the exact same node_modules folder. There's zero unique data here."
        ),
        space_impact=(
            "Typically 200MB-2GB per project. A developer with 10-20 projects can easily have "
            "10-40GB in node_modules alone. It regrows instantly when you run npm install - "
            "usually 30-120 seconds depending on project size and network speed."
        ),
        recovery_steps=[
            "cd into the project directory",
            "Run 'npm install' (or 'yarn install' if using Yarn)",
            "Wait 30-120 seconds for packages to download",
            "Your project is ready to use again",
        ],
        pro_tip=(
            "Consider using pnpm instead of npm. It uses hard links to share packages between "
            "projects, reducing disk usage by 50-80%. Install with 'npm install -g pnpm' then "
            "use 'pnpm install' instead of 'npm install'. Your existing projects work unchanged."
        ),
        edge_cases=(
            "If you have local/private packages not on npm (file: dependencies), ensure you have "
            "the source. Also, if you're offline frequently, consider keeping node_modules for "
            "active projects you need to work on without internet."
        ),
    ),
    "python_venvs": Category(
        id="python_venvs",
        name="Python Virtual Environments",
        paths=[],
        glob_patterns=["**/.venv", "**/venv", "**/.virtualenv", "**/env"],
        search_roots=["~/Documents", "~/Code", "~/Projects", "~/Developer", "~/repos", "~/src"],
        is_recursive=True,
        min_size_bytes=50 * 1024 * 1024,  # 50MB minimum
        risk_level=RiskLevel.SAFE,
        description="Python virtual environment directories",
        consequences="Recreate with 'python -m venv' and pip install",
        recovery="Recreate venv and reinstall from requirements.txt",
        what_is_it=(
            "Python virtual environments (.venv, venv, env) are isolated Python installations for "
            "each project. They contain a copy of the Python interpreter plus all pip-installed "
            "packages. This isolation prevents conflicts between projects that need different versions "
            "of the same package. Each venv is typically 100-500MB, with ML/AI projects reaching 2-5GB "
            "due to large packages like PyTorch, TensorFlow, or transformers."
        ),
        why_safe=(
            "Virtual environments contain only installed packages - nothing unique. Your requirements.txt "
            "or pyproject.toml lists dependencies. Running 'pip install -r requirements.txt' in a fresh "
            "venv recreates everything. If you use poetry or pipenv, their lock files ensure exact versions."
        ),
        space_impact=(
            "100-500MB for typical projects, 2-5GB for ML/AI projects with PyTorch/TensorFlow. "
            "A developer with 15 Python projects might have 5-15GB in venvs. Recreating takes "
            "1-5 minutes depending on packages and network speed."
        ),
        recovery_steps=[
            "cd into the project directory",
            "Run 'python -m venv .venv' to create fresh environment",
            "Run 'source .venv/bin/activate' to activate it",
            "Run 'pip install -r requirements.txt' (or 'poetry install' / 'pipenv install')",
        ],
        pro_tip=(
            "Use 'pip freeze > requirements.txt' before deleting to capture exact versions. "
            "For faster reinstalls, consider using 'uv' (https://github.com/astral-sh/uv) - "
            "it's 10-100x faster than pip for creating venvs and installing packages."
        ),
        edge_cases=(
            "If you have packages installed from local paths or private repos, ensure you have access "
            "to those sources. Check for any 'pip install -e .' editable installs that reference local code."
        ),
    ),
    "pycache": Category(
        id="pycache",
        name="Python Cache (__pycache__)",
        paths=[],
        glob_patterns=["**/__pycache__"],
        search_roots=["~/Documents", "~/Code", "~/Projects", "~/Developer", "~/repos", "~/src"],
        is_recursive=True,
        min_size_bytes=1 * 1024 * 1024,  # 1MB minimum (these are usually small)
        risk_level=RiskLevel.SAFE,
        description="Python bytecode cache directories",
        consequences="Python recompiles .py files on next import",
        recovery="Automatic - Python recreates on next run",
        what_is_it=(
            "__pycache__ directories contain compiled Python bytecode (.pyc files). When you import "
            "a Python module, Python compiles the .py source to bytecode and caches it in __pycache__. "
            "Next time you import, it uses the cached bytecode if the source hasn't changed - this "
            "speeds up startup. The bytecode is version-specific (e.g., cpython-311 for Python 3.11)."
        ),
        why_safe=(
            "Bytecode cache is purely derived from your .py source files. Python regenerates it "
            "automatically on the next import. There's zero unique content - it's just a performance "
            "optimization that can be recreated instantly."
        ),
        space_impact=(
            "Usually small - 1-50MB per project. But they accumulate in every directory with Python "
            "code, including inside packages. Total across all projects might be 100-500MB. "
            "Regeneration is instant (happens on first import, adds ~10ms per file)."
        ),
        recovery_steps=[
            "No action needed - Python recreates automatically",
            "Just run your Python code normally",
            "First run will be slightly slower (10-100ms) as bytecode is regenerated",
        ],
        pro_tip=(
            "Add '__pycache__/' to your .gitignore - these should never be committed. "
            "You can prevent creation entirely with 'export PYTHONDONTWRITEBYTECODE=1' but "
            "this slightly slows every Python startup."
        ),
    ),
    "build_artifacts": Category(
        id="build_artifacts",
        name="Build Artifacts",
        paths=[],
        glob_patterns=["**/dist", "**/build", "**/.build"],
        search_roots=["~/Documents", "~/Code", "~/Projects", "~/Developer", "~/repos", "~/src"],
        is_recursive=True,
        min_size_bytes=10 * 1024 * 1024,  # 10MB minimum
        risk_level=RiskLevel.REVIEW,
        description="Compiled build output directories",
        consequences="Need to rebuild projects",
        recovery="Run your project's build command",
        what_is_it=(
            "Build directories (dist, build, .build) contain compiled output from various build tools. "
            "'dist' typically holds distribution-ready files (webpack bundles, Python wheels). "
            "'build' is used by many tools (Create React App, Python setuptools, CMake). "
            "'.build' is common in Swift/iOS projects. These are intermediate files between your "
            "source code and the final runnable/deployable product."
        ),
        why_safe=(
            "Build artifacts are generated from your source code. Running your build command "
            "(npm run build, python -m build, swift build, etc.) recreates them. However, some "
            "build directories may contain cached data that speeds up subsequent builds - hence "
            "REVIEW level rather than SAFE."
        ),
        space_impact=(
            "10MB-500MB per project, occasionally 1GB+ for complex applications. Frontend projects "
            "with bundled assets can be especially large. Rebuilding takes 10 seconds to several "
            "minutes depending on project complexity."
        ),
        recovery_steps=[
            "cd into the project directory",
            "Run your build command (e.g., 'npm run build', 'python -m build', 'cargo build')",
            "First build will take full time (no incremental caching)",
        ],
        pro_tip=(
            "Keep build directories for projects you're actively working on - incremental builds "
            "are much faster than clean builds. Clean up old/inactive projects first."
        ),
        edge_cases=(
            "Some 'dist' or 'build' directories might contain manually placed files not generated "
            "by builds. Check if the directory is in .gitignore - if it is, it's safe to delete."
        ),
    ),
    "cargo_cache": Category(
        id="cargo_cache",
        name="Rust Cargo Cache",
        paths=["~/.cargo/registry", "~/.cargo/git"],
        risk_level=RiskLevel.SAFE,
        description="Rust crates.io package cache",
        consequences="Crates re-download on next build",
        recovery="Automatic - cargo fetches on build",
        what_is_it=(
            "Cargo is Rust's package manager. ~/.cargo/registry contains downloaded crate source code "
            "and compiled artifacts. ~/.cargo/git stores Git-based dependencies. Unlike npm, Cargo "
            "shares this cache across ALL Rust projects (no per-project duplication). The cache grows "
            "over time as you use more crates and can reach 5-20GB for active Rust developers."
        ),
        why_safe=(
            "All content is downloaded from crates.io or Git repositories. Your Cargo.toml and "
            "Cargo.lock files specify dependencies. Running 'cargo build' re-downloads and rebuilds "
            "everything. Compiled artifacts are just cached builds, not unique data."
        ),
        space_impact=(
            "3-20GB for active Rust developers. Moderate Rust usage might be 1-5GB. The cache "
            "grows indefinitely as old versions aren't automatically cleaned. Re-downloading "
            "typical deps takes 1-5 minutes; recompiling takes longer (10-30 minutes for large projects)."
        ),
        recovery_steps=[
            "No immediate action needed",
            "Run 'cargo build' in your project",
            "Cargo downloads missing crates automatically",
            "First build takes longer (downloading + compiling)",
        ],
        pro_tip=(
            "Use 'cargo cache' (install with 'cargo install cargo-cache') to see detailed usage "
            "and clean selectively. Run 'cargo cache --autoclean' to remove old versions while "
            "keeping recent ones."
        ),
    ),
    "go_cache": Category(
        id="go_cache",
        name="Go Module Cache",
        paths=["~/go/pkg/mod", "~/Library/Caches/go-build"],
        risk_level=RiskLevel.SAFE,
        description="Go module downloads and build cache",
        consequences="Modules re-download on next build",
        recovery="Automatic - go fetches on build",
        cleanup_command="go clean -modcache",
        what_is_it=(
            "Go stores downloaded modules in ~/go/pkg/mod (or $GOPATH/pkg/mod). The build cache "
            "in ~/Library/Caches/go-build stores compiled packages for faster incremental builds. "
            "Like Cargo, Go shares this cache across all projects. It grows as you use more "
            "third-party packages and can reach 2-10GB for active Go developers."
        ),
        why_safe=(
            "All modules are downloaded from their source repositories (GitHub, etc.) based on "
            "your go.mod and go.sum files. The sum file ensures you get exactly the same content. "
            "Running 'go build' or 'go mod download' restores everything."
        ),
        space_impact=(
            "1-10GB for active Go developers. Smaller than Rust typically because Go compiles "
            "faster and the community has fewer massive dependencies. Re-downloading takes "
            "1-3 minutes; rebuilding is fast (Go compiles quickly)."
        ),
        recovery_steps=[
            "cd into your Go project",
            "Run 'go mod download' to pre-fetch dependencies",
            "Or just run 'go build' - it downloads automatically",
            "First build downloads missing modules",
        ],
        pro_tip=(
            "Set GOPROXY=https://proxy.golang.org for faster, more reliable downloads. "
            "Use 'go clean -cache' to clear just the build cache (keeps downloaded modules)."
        ),
    ),
    "target_dirs": Category(
        id="target_dirs",
        name="Rust Target Directories",
        paths=[],
        glob_patterns=["**/target"],
        search_roots=["~/Documents", "~/Code", "~/Projects", "~/Developer", "~/repos", "~/src"],
        is_recursive=True,
        min_size_bytes=100 * 1024 * 1024,  # 100MB minimum (Rust targets are large)
        risk_level=RiskLevel.SAFE,
        description="Rust compilation output directories",
        consequences="Next cargo build does full recompile",
        recovery="Run 'cargo build' to recompile",
        what_is_it=(
            "The 'target' directory in Rust projects contains all compilation artifacts: debug builds, "
            "release builds, dependency compilations, and incremental build caches. Rust compiles "
            "each dependency from source, so even small projects can have 500MB-2GB targets. "
            "Complex projects with many dependencies can reach 5-10GB per project."
        ),
        why_safe=(
            "Everything in target is compiled from your source code and dependencies. Your Cargo.toml "
            "and Cargo.lock define the project. Running 'cargo build' recreates everything, though "
            "it takes time since Rust compilation is thorough."
        ),
        space_impact=(
            "500MB-5GB per project is common. Active Rust developers with multiple projects "
            "can easily have 20-50GB in target directories. First rebuild takes 5-30 minutes "
            "depending on project size. Incremental builds are much faster (seconds)."
        ),
        recovery_steps=[
            "cd into the Rust project",
            "Run 'cargo build' for debug or 'cargo build --release' for release",
            "First build compiles all dependencies (5-30 minutes)",
            "Subsequent builds are incremental (seconds)",
        ],
        pro_tip=(
            "Use 'cargo clean' to remove just one project's target. For shared dependencies, "
            "consider using 'cargo build --target-dir ~/.cargo/target' to share build artifacts "
            "across projects (experimental, can cause issues). Or use sccache for distributed caching."
        ),
    ),
    "dotnet_cache": Category(
        id="dotnet_cache",
        name=".NET/NuGet Cache",
        paths=["~/.nuget/packages", "~/.dotnet"],
        risk_level=RiskLevel.SAFE,
        description=".NET SDK and NuGet package cache",
        consequences="Packages re-download on next build",
        recovery="Run 'dotnet restore' to re-download",
        cleanup_command="dotnet nuget locals all --clear",
        what_is_it=(
            "NuGet is .NET's package manager. ~/.nuget/packages stores downloaded packages shared "
            "across all .NET projects. ~/.dotnet contains SDK installations and tools. Like other "
            "modern package managers, NuGet shares packages globally rather than per-project copies."
        ),
        why_safe=(
            "All packages are downloaded from nuget.org or configured package sources. Your .csproj "
            "and packages.lock.json specify dependencies. Running 'dotnet restore' re-downloads everything."
        ),
        space_impact=(
            "2-10GB typical. .NET SDK itself is 1-3GB per version. Package cache grows over time. "
            "Re-downloading takes 1-5 minutes depending on package count."
        ),
        recovery_steps=[
            "Run 'dotnet restore' in your solution directory",
            "Packages download automatically",
            "Or just run 'dotnet build' - it restores first",
        ],
        pro_tip=(
            "Use 'dotnet nuget locals all --list' to see cache locations. Clean http-cache and "
            "temp separately from packages if you want faster restores but smaller disk usage."
        ),
    ),
}


def get_category(category_id: str) -> Category | None:
    """Get a category by ID."""
    return CATEGORIES.get(category_id)


def get_all_categories() -> list[Category]:
    """Get all categories."""
    return list(CATEGORIES.values())


def get_safe_categories() -> list[Category]:
    """Get all safe categories."""
    return [c for c in CATEGORIES.values() if c.risk_level == RiskLevel.SAFE]


def get_review_categories() -> list[Category]:
    """Get all categories that need review."""
    return [c for c in CATEGORIES.values() if c.risk_level == RiskLevel.REVIEW]


def get_risky_categories() -> list[Category]:
    """Get all risky categories."""
    return [c for c in CATEGORIES.values() if c.risk_level == RiskLevel.RISKY]
