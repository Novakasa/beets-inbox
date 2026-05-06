{
  description = "beets-inbox — self-hosted music inbox for beets";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
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

        # ── NixOS module test ─────────────────────────────────────────────────
        checks.nixos-module = pkgs.testers.nixosTest {
          name = "beets-inbox-module";

          nodes.machine = { ... }: {
            imports = [ self.nixosModules.default ];
            services.beets-inbox = {
              enable = true;
              inboxPath = "/var/lib/beets-inbox/inbox";
            };
            # Allow the test script to reach the service
            networking.firewall.allowedTCPPorts = [ 8085 ];
          };

          testScript = ''
            machine.wait_for_unit("beets-inbox.service")
            machine.wait_for_open_port(8085)

            # API responds
            out = machine.succeed("curl -sf http://localhost:8085/api/inbox")
            assert out.strip() == "[]", f"Expected empty inbox, got: {out!r}"

            # Frontend is served
            machine.succeed("curl -sf http://localhost:8085/ | grep -q 'beets-inbox'")
          '';
        };

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
      nixosModules.default = { pkgs, lib, ... }: {
        imports = [ ./nix/module.nix ];
        config.services.beets-inbox.package = lib.mkDefault
          self.packages.${pkgs.system}.default;
      };
    };
}
