{
  description = "beets-inbox — self-hosted music inbox for beets";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # NixOS module — exported for all systems
      nixosModule = import ./nix/module.nix;
    in
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # ── Python package ────────────────────────────────────────────────────
        pythonDeps = ps: with ps; [
          fastapi
          uvicorn
          watchdog
          python-multipart
          mutagen
        ];

        beetsInboxPython = python.withPackages pythonDeps;

        beetsInboxPackage = python.pkgs.buildPythonApplication {
          pname = "beets-inbox";
          version = "0.1.0";
          pyproject = true;

          src = ./backend;

          build-system = with python.pkgs; [ hatchling ];

          dependencies = pythonDeps python.pkgs;

          # Bundle the pre-built Elm frontend
          postInstall = ''
            install -Dm644 ${./frontend/dist/index.html} \
              $out/share/beets-inbox/frontend/index.html
            install -Dm644 ${./frontend/dist/main.js} \
              $out/share/beets-inbox/frontend/main.js
          '';

          # Runtime dep: beets must be on PATH for subprocess calls
          makeWrapperArgs = [
            "--prefix" "PATH" ":" "${pkgs.beets}/bin"
          ];

          meta = {
            description = "Self-hosted music inbox for beets";
            mainProgram = "beets-inbox";
          };
        };
      in
      {
        # ── Package ───────────────────────────────────────────────────────────
        packages.default = beetsInboxPackage;

        # ── Dev shell ─────────────────────────────────────────────────────────
        devShells.default = pkgs.mkShell {
          packages = [
            # Python
            python
            pkgs.uv

            # Beets
            pkgs.beets

            # Elm
            pkgs.elmPackages.elm
            pkgs.elmPackages.elm-format

            # Tools
            pkgs.sqlite
            pkgs.just
            pkgs.sox
          ];

          shellHook = ''
            echo "beets-inbox dev shell"
            echo "  python: $(python3 --version)"
            echo "  beet:   $(beet version | head -1)"
            echo "  elm:    $(elm --version)"
            echo "  uv:     $(uv --version)"
          '';

          env = {
            UV_PYTHON = "${python}/bin/python3";
          };
        };
      }
    ) // {
      # ── NixOS module (system-independent) ────────────────────────────────
      nixosModules.default = nixosModule;
    };
}
