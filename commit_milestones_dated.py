#!/usr/bin/env python3
"""
commit_milestones_dated.py - Modified version with date support
Allows backdating commits for milestone simulation.
"""

import json
import os
import subprocess
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import glob
import random

class MilestoneCommitter:
    def __init__(self, repo_path: str, manifest_path: str, state_path: str, 
                 dry_run: bool = False, allow_empty: bool = False, 
                 verbose: bool = False, start_date: Optional[str] = None):
        self.repo_path = Path(repo_path).resolve()
        self.manifest_path = Path(manifest_path)
        if not self.manifest_path.is_absolute():
            self.manifest_path = self.repo_path / self.manifest_path
        
        self.state_path = Path(state_path)
        if not self.state_path.is_absolute():
            self.state_path = self.repo_path / self.state_path
        
        self.dry_run = dry_run
        self.allow_empty = allow_empty
        self.verbose = verbose
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.now()
        
        self._validate_environment()
        self.milestones = self._load_milestones()
        self.completed = self._load_completed()
        
    def _validate_environment(self):
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")
        
        if not self.repo_path.is_dir():
            raise ValueError(f"Repository path is not a directory: {self.repo_path}")
        
        # Check if it's a git repo
        result = subprocess.run(
            ['git', '-C', str(self.repo_path), 'rev-parse', '--is-inside-work-tree'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise ValueError(f"Not a git repository: {self.repo_path}")
        
        if not self.manifest_path.exists():
            raise ValueError(f"Manifest file not found: {self.manifest_path}")
        
    def _load_milestones(self) -> List[Dict]:
        with open(self.manifest_path, 'r') as f:
            data = json.load(f)
        return data.get('milestones', [])
    
    def _load_completed(self) -> List[str]:
        if not self.state_path.exists():
            return []
        
        try:
            with open(self.state_path, 'r') as f:
                data = json.load(f)
                return data.get('completed', [])
        except:
            return []
    
    def _save_completed(self, completed: List[str]):
        with open(self.state_path, 'w') as f:
            json.dump({'completed': completed}, f, indent=2)
    
    def _run_git(self, args: List[str], env: Optional[Dict] = None) -> bool:
        """Run git command with optional environment variables for date"""
        cmd = ['git', '-C', str(self.repo_path)] + args
        if self.verbose:
            print(f"  $ {' '.join(cmd)}")
        
        if self.dry_run:
            return True
        
        try:
            # Merge environment with custom date env vars
            git_env = os.environ.copy()
            if env:
                git_env.update(env)
            
            result = subprocess.run(cmd, env=git_env, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error: {result.stderr}")
                return False
            return True
        except Exception as e:
            print(f"Error running git: {e}")
            return False
    
    def _get_date_for_milestone(self, index: int) -> datetime:
        """Calculate date for each milestone, spread over 5 months"""
        if len(self.milestones) <= 1:
            return self.start_date
        
        # Spread commits over 5 months (150 days)
        total_days = 150
        spacing = total_days / (len(self.milestones) - 1)
        days_offset = int(index * spacing)
        
        # Add some randomness to make it look more natural
        random.seed(index)  # Consistent randomness
        days_offset += random.randint(-3, 3)
        days_offset = max(0, days_offset)
        
        return self.start_date + timedelta(days=days_offset)
    
    def _create_milestone_files(self, patterns: List[str]):
        """Create dummy files for milestone paths so we have something to commit"""
        for pattern in patterns:
            # Handle glob patterns like src/modules/**/dto
            if '**' in pattern or '*' in pattern:
                # Create a dummy file in the directory structure
                base_path = pattern.replace('**', '').replace('*', '').strip('/')
                if base_path:
                    full_path = self.repo_path / base_path
                    full_path.mkdir(parents=True, exist_ok=True)
                    placeholder = full_path / '.placeholder'
                    placeholder.write_text(f'Milestone placeholder file\nCreated: {datetime.now()}')
            else:
                # Simple path - create file with dummy content
                full_path = self.repo_path / pattern
                if not full_path.exists():
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    if not pattern.endswith('/'):  # Not a directory
                        if pattern.endswith('.json'):
                            full_path.write_text('{}\n')
                        elif pattern.endswith('.yml') or pattern.endswith('.yaml'):
                            full_path.write_text('# Placeholder configuration\n')
                        elif pattern.endswith('.md'):
                            full_path.write_text(f'# {pattern}\n\nPlaceholder documentation\n')
                        elif pattern.endswith('.ts') or pattern.endswith('.js'):
                            full_path.write_text('// Placeholder code\n')
                        else:
                            full_path.write_text('Placeholder content\n')
    
    def commit_milestone(self, milestone: Dict, index: int) -> bool:
        """Commit a single milestone with backdated date"""
        mid = milestone['id']
        message = milestone['message']
        patterns = milestone.get('paths', [])
        
        # Check if already completed
        if mid in self.completed:
            print(f"✅ Milestone {mid} already completed")
            return True
        
        print(f"\n📦 Milestone: {mid}")
        print(f"   Message: {message}")
        print(f"   Paths: {', '.join(patterns)}")
        
        # Create files if they don't exist (for simulation)
        self._create_milestone_files(patterns)
        
        # Resolve paths
        resolved = []
        for pattern in patterns:
            # Simple resolution - add all matching files
            full_path = self.repo_path / pattern
            if full_path.exists():
                resolved.append(str(full_path))
            else:
                # Try with glob
                glob_pattern = str(self.repo_path / pattern)
                matches = glob.glob(glob_pattern, recursive=True)
                resolved.extend(matches)
        
        if not resolved and not self.allow_empty:
            print(f"   ⚠️ No files found for milestone {mid}, skipping")
            return False
        
        # Get date for this milestone
        commit_date = self._get_date_for_milestone(index)
        date_str = commit_date.strftime('%Y-%m-%d %H:%M:%S')
        print(f"   📅 Commit date: {date_str}")
        
        # Set environment variables for git
        git_env = {
            'GIT_AUTHOR_DATE': date_str,
            'GIT_COMMITTER_DATE': date_str
        }
        
        if self.dry_run:
            print(f"   🔍 [DRY RUN] Would commit with date: {date_str}")
            return True
        
        # Stage files
        if resolved:
            if not self._run_git(['add', '--'] + resolved, git_env):
                return False
            
            # Check if there are staged changes
            result = subprocess.run(
                ['git', '-C', str(self.repo_path), 'diff', '--cached', '--quiet'],
                capture_output=True
            )
            has_changes = result.returncode != 0
            
            if not has_changes and not self.allow_empty:
                print(f"   ⚠️ No changes to commit for {mid}")
                self._run_git(['reset'], git_env)
                return False
        
        # Commit
        commit_args = ['commit', '-m', message]
        if self.allow_empty or not resolved:
            commit_args.append('--allow-empty')
        
        if not self._run_git(commit_args, git_env):
            return False
        
        # Mark as completed
        self.completed.append(mid)
        self._save_completed(self.completed)
        print(f"   ✅ Committed: {mid} on {date_str}")
        return True
    
    def run(self):
        """Run the milestone commit process"""
        print("\n🚀 Starting milestone commit process...")
        print(f"📁 Repository: {self.repo_path}")
        print(f"📄 Manifest: {self.manifest_path}")
        print(f"📅 Start date: {self.start_date.strftime('%Y-%m-%d')}")
        print(f"   (Commits will be spread over 5 months)")
        
        if self.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        
        successful = 0
        failed = 0
        skipped = 0
        
        for i, milestone in enumerate(self.milestones):
            try:
                if self.commit_milestone(milestone, i):
                    successful += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"❌ Error committing {milestone['id']}: {e}")
                failed += 1
        
        print("\n📊 Summary:")
        print(f"   ✅ Successful: {successful}")
        print(f"   ⏭️  Skipped: {skipped}")
        print(f"   ❌ Failed: {failed}")
        
        if not self.dry_run and successful > 0:
            print(f"\n💡 To push to GitHub:")
            print(f"   cd {self.repo_path}")
            print(f"   git push origin main")
        
        return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description='Commit milestones with backdated dates (for simulation)'
    )
    parser.add_argument('--repo', default='.', help='Path to git repository')
    parser.add_argument('--manifest', default='milestones.json', help='Path to milestones manifest')
    parser.add_argument('--state', default='.milestone_progress.json', help='Path to progress state')
    parser.add_argument('--start-date', default='2026-07-01', help='Start date for first commit (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without committing')
    parser.add_argument('--allow-empty', action='store_true', help='Allow empty commits')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    try:
        committer = MilestoneCommitter(
            repo_path=args.repo,
            manifest_path=args.manifest,
            state_path=args.state,
            dry_run=args.dry_run,
            allow_empty=args.allow_empty,
            verbose=args.verbose,
            start_date=args.start_date
        )
        
        success = committer.run()
        sys.exit(0 if success else 1)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()