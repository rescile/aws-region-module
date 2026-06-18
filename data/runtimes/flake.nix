{
  description = "AWS Deployment Framework";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.awscli2

          (pkgs.python3.withPackages (ps: [
            ps.boto3
            ps.botocore
            ps.gql
            ps.requests
            ps.requests-toolbelt
          ]))
        ];

        shellHook = ''
          echo "AWS SDK Loaded"
          echo "Python version: $(python --version)"

          export PRJ_ROOT="$PWD"
          export PYTHONPATH="$PRJ_ROOT:$PYTHONPATH"
        '';
      };
    };
}
