{
  description = "beets-inbox — self-hosted music inbox for beets";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      nixosModule = import ./nix/module.nix;
    in
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # ── Elm frontend ──────────────────────────────────────────────────────
        elmFrontend = pkgs.stdenv.mkDerivation {
          name = "beets-inbox-frontend";
          src = ./frontend;

          nativeBuildInputs = [ pkgs.elmPackages.elm ];

          buildPhase = pkgs.elmPackages.fetchElmDeps {
            elmPackages = import ./nix/elm-srcs.nix;
            elmVersion = "0.19.1";
            registryDat = ./nix/registry.dat;
          };

          installPhase = ''
            elm make src/Main.elm --optimize --output=$out/main.js
            cp ${./frontend/index.html} $out/index.html
          '';
        };

        # ── Python package ────────────────────────────────────────────────────
        pythonDeps = ps: with ps; [
          fastapi
          uvicorn
          watchdog
          python-multipart
          mutagen
        ];

        beetsInboxPackage = python.pkgs.buildPythonApplication {
          pname = "beets-inbox";
          version = "0.1.0";
          pyproject = true;

          src = ./backend;

          build-system = with python.pkgs; [ hatchling ];

          dependencies = pythonDeps python.pkgs;

          postInstall = ''
            install -Dm644 ${elmFrontend}/index.html \
              $out/share/beets-inbox/frontend/index.html
            install -Dm644 ${elmFrontend}/main.js \
              $out/share/beets-inbox/frontend/main.js
          '';

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
        packages.default = beetsInboxPackage;

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
            pkgs.elmPackages.elm-language-server
            pkgs.haskellPackages.elm2nix

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
      nixosModules.default = nixosModule;
    };
}
