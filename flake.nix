{
  description = "AWS Deployment & Pulumi Graph Orchestration Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    sfdx-nix.url = "github:rfaulhaber/sfdx-nix";
  };

  outputs = { self, nixpkgs, sfdx-nix }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      sf-cli = sfdx-nix.packages.${system}.default;
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.awscli2
          #pkgs.pulumi
          sf-cli

          (pkgs.python3.withPackages (ps: [
            ps.boto3
            ps.botocore
            #ps.pulumi
            #ps.pulumi-aws
            ps.gql
            ps.requests
            ps.simple-salesforce
          ]))
        ];

        shellHook = ''
          echo "AWS and Salesforce Python SDK Loaded"
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
