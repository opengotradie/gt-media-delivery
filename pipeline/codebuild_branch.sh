#!/bin/bash

export CI=true
export CODEBUILD=true

export CurrentBranch=`git symbolic-ref HEAD --short 2>/dev/null`
if [ "$CurrentBranch" == "" ] ; then
  CurrentBranch=`git branch -a --contains HEAD | sed -n 2p | awk '{ printf $1 }'`
  export CurrentBranch=${CurrentBranch#remotes/origin/}
fi

env="$CurrentBranch"
if [ "$CurrentBranch" == "master" ] ; then
  env="dev"
fi
export Environment=$env
echo "$Environment"