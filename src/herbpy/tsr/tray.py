import numpy, prpy
from prpy.tsr.tsrlibrary import TSRFactory
from prpy.tsr.tsr import TSR, TSRChain

@TSRFactory('herb', 'wicker_tray', 'point_on')
def point_on(robot, tray, manip=None, padding=0.0):
    '''
    This creates a TSR that allows you to sample poses on the tray.
    The samples from this TSR should be used to find points for object placement.
    They are directly on the tray, and thus not suitable as an end-effector pose.
    Grasp specific calculations are necessary to find a suitable end-effector pose.

    @param robot The robot performing the grasp
    @param tray The tray to sample poses on
    @param manip The manipulator to perform the grasp, if None
       the active manipulator on the robot is used
    @param padding The amount of space around the edge to exclude from sampling
       If using this to place an object, this would be the maximum radius of the object
    '''
    if manip is None:
        manip_idx = robot.GetActiveManipulatorIndex()
    else:
        with manip.GetRobot():
            manip.SetActive()
            manip_idx = manip.GetRobot().GetActiveManipulatorIndex()
            
    T0_w = tray.GetTransform()

    # The frame is set on the ta such that the y-axis is normal to the table surface
    Tw_e = numpy.eye(4)
    Tw_e[2,3] = 0.04 # set the object on top of the tray

    Bw = numpy.zeros((6,2))

    # TODO - replace this with hard coded extents that make sense, this won't work
    #  right if the tray isn't axis-aligned
    xdim = 0.235 - 2.*padding #tray_extents[0] - 2.*padding
    ydim = 0.33 - 2.*padding #tray_extents[1] - 2.*padding
    Bw[0,:] = [-xdim, xdim ] # move along x and z directios to get any point on tray
    Bw[1,:] = [-ydim, ydim]
    Bw[2,:] = [-0.02, 0.04] # verticle movement
    Bw[5,:] = [-numpy.pi, numpy.pi] # allow any rotation around z - which is the axis normal to the tray top

    
    tray_top_tsr = TSR(T0_w = T0_w, Tw_e = Tw_e, Bw = Bw, manip = manip_idx)
    tray_top_chain = TSRChain(sample_start = False, sample_goal = True, constrain=False, 
                               TSR = tray_top_tsr)
    return [tray_top_chain]


@TSRFactory('herb', 'wicker_tray', 'handle_grasp')
def handle_grasp(robot, tray, manip=None, handle=None):
    '''
    This creates a TSR for grasping the left handle of the tray
    By default, the handle is grasped with the left hand, unless manip is specified

    @param robot The robot performing the grasp
    @param tray The tray to grasp
    @param manip The manipulator to perform the grasp, if None
      the active manipulator on the robot is used
    '''
    if manip is None:
        manip_idx = robot.GetActiveManipulatorIndex()
    else:
        with manip.GetRobot():
            manip.SetActive()
            manip_idx = manip.GetRobot().GetActiveManipulatorIndex()
            
    tray_in_world = tray.GetTransform()

    # Compute the pose of both handles in the tray
    handle_one_in_tray = numpy.eye(4)
    handle_one_in_tray[1,3] = -0.33
    
    handle_two_in_tray = numpy.eye(4)
    handle_two_in_tray[1,3] = 0.33

    handle_poses = [handle_one_in_tray, handle_two_in_tray]

    # Define the grasp relative to a particular handle
    grasp_in_handle = numpy.array([[0.,  1.,  0., 0.],
                                   [1.,  0.,  0., 0.],
                                   [0.,  0., -1., 0.33],
                                   [0.,  0.,  0., 1.]])

    Bw = numpy.zeros((6,2))
    epsilon = 0.03
    Bw[0,:] = [0., epsilon] # Move laterally along handle
    Bw[2,:] = [-0.01, 0.01] # Move up or down a little bit
    Bw[5,:] = [-5.*numpy.pi/180., 5.*numpy.pi/180.] # Allow 5 degrees of yaw

    # Now build tsrs for both
    chains = []
    best_dist = float('inf')
    for handle_in_tray in handle_poses:
        dist = numpy.linalg.norm(handle_in_tray[:2,3] - manip.GetEndEffectorTransform()[:2,3])
        if handle == 'closest' and dist > best_dist:
            continue
        handle_in_world = numpy.dot(tray_in_world, handle_in_tray)
        tray_grasp_tsr = TSR(T0_w = handle_in_world, 
                             Tw_e = grasp_in_handle, 
                             Bw = Bw, 
                             manip=manip_idx)
        tray_grasp_chain = TSRChain(sample_start = False, 
                                    sample_goal = True, 
                                    constrain=False,
                                    TSR = tray_grasp_tsr)
        if handle == 'closest':
            chains = []
        chains.append(tray_grasp_chain)
    return chains

@TSRFactory('herb', 'wicker_tray', 'lift')
def lift(robot, tray, distance=0.1):
    '''
    This creates a TSR for lifting the tray a specified distance with both arms
    It is assumed that when called, the robot is grasping the tray with both arms

    @param robot The robot to perform the lift
    @param tray The tray to lift
    @param distance The distance to lift the tray
    '''
    print 'distance = %0.2f' % distance

    with robot:
        robot.left_arm.SetActive()
        left_manip_idx = robot.GetActiveManipulatorIndex()

        robot.right_arm.SetActive()
        right_manip_idx = robot.GetActiveManipulatorIndex()

    # First create a goal for the right arm that is 
    #  the desired distance above the current tray pose
    left_in_world = robot.left_arm.GetEndEffectorTransform()
    desired_handle_in_world = tray.GetTransform()

    desired_handle_in_world[:3,3] = left_in_world[:3,3]
    left_in_handle = numpy.dot(numpy.linalg.inv(desired_handle_in_world), left_in_world)
    desired_handle_in_world[2,3] += distance

    Bw_goal = numpy.zeros((6,2))
    epsilon = 0.05
    Bw_goal[0,:] = [-epsilon, epsilon]
    Bw_goal[1,:] = [-epsilon, epsilon]
    Bw_goal[2,:] = [-epsilon, epsilon]
    Bw_goal[3,:] = [-epsilon, epsilon]

    tsr_left_goal = TSR(T0_w = desired_handle_in_world, 
                     Tw_e = left_in_handle,
                     Bw = Bw_goal,
                     manip=left_manip_idx)
    goal_left_chain = TSRChain(sample_start = False, sample_goal = True, constrain=False,
                          TSRs = [tsr_left_goal])

    right_in_world = robot.right_arm.GetEndEffectorTransform()
    new_desired_handle_in_world = tray.GetTransform()
    new_desired_handle_in_world[:3,3] = right_in_world[:3,3]
    right_in_handle = numpy.dot(numpy.linalg.inv(new_desired_handle_in_world), right_in_world)
    new_desired_handle_in_world[2,3] += distance

    tsr_right_goal = TSR(T0_w = new_desired_handle_in_world, 
                     Tw_e = right_in_handle,
                     Bw = Bw_goal,
                     manip=right_manip_idx)
    goal_right_chain = TSRChain(sample_start = False, sample_goal = True, constrain=False,
                          TSRs = [tsr_right_goal])

    # Create a constrained chain for the left arm that keeps it
    #  in the appropriate pose relative to the right arm
    right_in_left = numpy.dot(numpy.linalg.inv(left_in_world),
                              right_in_world)
                                               
    Bw = numpy.zeros((6,2))
    epsilon = 0.1
    Bw[0,:] = [-epsilon, epsilon]
    Bw[1,:] = [-epsilon, epsilon]
    Bw[2,:] = [-epsilon, epsilon]
    Bw[3,:] = [-epsilon, epsilon]
    tsr_0 = TSR(T0_w = numpy.eye(4),
                Tw_e = right_in_left,
                Bw = Bw,
                manip=right_manip_idx,
                bodyandlink='%s %s' % (robot.GetName(), robot.left_arm.GetEndEffector().GetName()))
    movement_chain = TSRChain(sample_start = False, sample_goal = False, constrain=True,
                              TSRs = [tsr_0])
    
    return [movement_chain, goal_right_chain, goal_left_chain]

@TSRFactory('herb', 'wicker_tray', 'pull')
def pull_tray(robot, tray, manip=None, distance=0.0, direction=[1., 0., 0.], 
              angular_tolerance=[0., 0., 0.],  position_tolerance=[0., 0., 0.]):
    """
    This creates a TSR for pulling the tray in a specified direction for a specified distance
    It is assumed that when called, the robot is grasping the tray

    @param robot The robot to perform the lift
    @param tray The tray to lift
    @param manip The manipulator to pull with (if None the active manipulator is used)
    @param distance The distance to lift the tray
    @param angular_tolerance A 3x1 vector describing the tolerance of the pose of the end-effector
          in roll, pitch and yaw relative to a coordinate frame with z pointing in the pull direction
    @param position_tolerance A 3x1 vector describing the tolerance of the pose of the end-effector
          in x, y and z relative to a coordinate frame with z pointing in the pull direction
    """
    if manip is None:
        manip = robot.GetActiveManipulator()
        manip_idx = robot.GetActiveManipulatorIndex()
    else:
        with manip.GetRobot():
            manip.SetActive()
            manip_idx = manip.GetRobot().GetActiveManipulatorIndex()
            
    # Create a w frame with z-axis pointing in direction of pull
    ee_in_world = manip.GetEndEffectorTransform()
    w_in_world = prpy.kin.H_from_op_diff(ee_in_world[:3,3], direction)

    # Move the w frame the appropriate distance along the pull direction
    end_in_w = numpy.eye(4)
    end_in_w[2,3] = distance
    desired_w_in_world = numpy.dot(w_in_world, end_in_w)

    # Compute the current end-effector in w frame
    ee_in_w = numpy.dot(numpy.linalg.inv(w_in_world), ee_in_world)

    Bw_goal = numpy.zeros((6,2))
    Bw_goal[0,:] = [-position_tolerance[0], position_tolerance[0]]
    Bw_goal[1,:] = [-position_tolerance[1], position_tolerance[1]]
    Bw_goal[2,:] = [-position_tolerance[2], position_tolerance[2]]
    Bw_goal[3,:] = [-angular_tolerance[0], angular_tolerance[0]]
    Bw_goal[4,:] = [-angular_tolerance[1], angular_tolerance[1]]
    Bw_goal[5,:] = [-angular_tolerance[2], angular_tolerance[2]]
    
    goal_tsr = TSR(T0_w = desired_w_in_world,
                   Tw_e = ee_in_w,
                   Bw = Bw_goal,
                   manip = manip_idx)

    goal_tsr_chain = TSRChain(sample_start=False, 
                              sample_goal=True, 
                              constrain=False,
                              TSRs=[goal_tsr])

    Bw_constraint = numpy.zeros((6,2))
    Bw_constraint[0,:] = [-position_tolerance[0], position_tolerance[0]]
    Bw_constraint[1,:] = [-position_tolerance[1], position_tolerance[1]]
    Bw_constraint[2,:] = [-position_tolerance[2], distance + position_tolerance[2]]
    Bw_constraint[3,:] = [-angular_tolerance[0], angular_tolerance[0]]
    Bw_constraint[4,:] = [-angular_tolerance[1], angular_tolerance[1]]
    Bw_constraint[5,:] = [-angular_tolerance[2], angular_tolerance[2]]

    traj_tsr = TSR(T0_w = w_in_world,
                   Tw_e = ee_in_w,
                   Bw = Bw_constraint,
                   manip = manip_idx)
    traj_tsr_chain = TSRChain(sample_start=False,
                              sample_goal=False,
                              constrain=True,
                              TSRs = [traj_tsr])
    
    return [goal_tsr_chain, traj_tsr_chain]
