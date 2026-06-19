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
            ps.pyjwt
            ps.simple-salesforce
            ps.cryptography
          ]))
        ];

        shellHook = ''
          echo "AWS SDK Loaded"
          echo "Python version: $(python --version)"

          export AWS_DEFAULT_REGION="eu-central-2"

          # ==============================================================================
          # CRITICAL ROUTING FIX: Module Resolution Paths
          # ==============================================================================
          # Captures the absolute root location of your repo and injects your nested
          # project layout into Python's native system search scope globally.
          export PRJ_ROOT="$PWD"
          export PYTHONPATH="$PRJ_ROOT/project:$PYTHONPATH"
          # ==============================================================================

          # 1. Automate local state login
          #export PULUMI_BACKEND_URL="file://~"
          #pulumi login --local > /dev/null 2>&1

          # 2. Automate the encryption passphrase
          #if [ -z "$PULUMI_CONFIG_PASSPHRASE" ]; then
          #  export PULUMI_CONFIG_PASSPHRASE="local-dev-rescile-secret-key"
          #fi
        '';
      };
    };
}
