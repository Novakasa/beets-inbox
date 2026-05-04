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
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            # Python
            python
            pkgs.uv

            # Beets
            (pkgs.beets.override {
              pluginOverrides = {
                chroma.enable = true;
                fetchart.enable = true;
                embedart.enable = true;
              };
            })

            # Elm
            pkgs.elmPackages.elm
            pkgs.elmPackages.elm-format

            # Tools
            pkgs.sqlite
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
    );
}
